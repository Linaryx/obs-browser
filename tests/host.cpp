#include <obs.h>
#include <obs-nix-platform.h>
#include <graphics/graphics.h>
#include <util/platform.h>
#include <QApplication>
#include <QTimer>
#include <QImage>
#include <QDir>
#include <X11/Xlib.h>
#include <wayland-client.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <vector>

static std::atomic<uint64_t> audio_frames{0};
static void audio_capture(void *, obs_source_t *, const audio_data *data, bool muted)
{
	if (!muted && data->data[0]) {
		const float *samples = reinterpret_cast<const float *>(data->data[0]);
		for (uint32_t i = 0; i < data->frames; ++i) {
			if (samples[i] > .001f || samples[i] < -.001f) {
				audio_frames += data->frames;
				break;
			}
		}
	}
}

int main(int argc, char **argv)
{
	QApplication app(argc, argv);
	if (argc < 6) {
		fprintf(stderr, "Usage: host PLUGIN DATA FIXTURE OUTPUT_DIR COUNT [SECONDS]\n");
		return 2;
	}
	const int count = std::atoi(argv[5]);
	const int seconds = argc > 6 ? std::atoi(argv[6]) : 20;
	const int requested_width = qEnvironmentVariableIntValue("OBS_BROWSER_TEST_WIDTH");
	const int requested_height = qEnvironmentVariableIntValue("OBS_BROWSER_TEST_HEIGHT");
	const int width = requested_width > 0 ? requested_width : 1280;
	const int height = requested_height > 0 ? requested_height : 720;
	if (width < 256 || height < 256 || width > 8192 || height > 8192 || count < 1 || count > 16 || seconds < 1) {
		return 2;
	}
	QDir().mkpath(argv[4]);
	const auto config = QString(argv[4]) + "/config";
	QDir().mkpath(config);
	const bool wayland = qEnvironmentVariable("QT_QPA_PLATFORM") == "wayland";
	void *display = wayland ? (void *)wl_display_connect(nullptr) : (void *)XOpenDisplay(nullptr);
	if (!display) {
		return 3;
	}
	obs_set_nix_platform(wayland ? OBS_NIX_PLATFORM_WAYLAND : OBS_NIX_PLATFORM_X11_EGL);
	obs_set_nix_platform_display(display);
	obs_set_cmdline_args(argc, argv);
	if (!obs_startup("en-US", config.toUtf8().constData(), nullptr)) {
		return 4;
	}
	obs_audio_info ai{};
	ai.samples_per_sec = 48000;
	ai.speakers = SPEAKERS_STEREO;
	if (!obs_reset_audio(&ai)) {
		return 5;
	}
	obs_video_info vi{};
	vi.graphics_module = "libobs-opengl.so";
	vi.fps_num = 60;
	vi.fps_den = 1;
	vi.base_width = vi.output_width = width;
	vi.base_height = vi.output_height = height;
	vi.output_format = VIDEO_FORMAT_RGBA;
	vi.colorspace = VIDEO_CS_709;
	vi.range = VIDEO_RANGE_FULL;
	vi.scale_type = OBS_SCALE_BILINEAR;
	if (obs_reset_video(&vi) != OBS_VIDEO_SUCCESS) {
		return 6;
	}
	obs_data_t *priv = obs_get_private_data();
	obs_data_set_bool(priv, "BrowserHWAccel", true);
	obs_data_release(priv);
	obs_module_t *module = nullptr;
	if (obs_open_module(&module, argv[1], argv[2]) != MODULE_SUCCESS || !obs_init_module(module)) {
		return 7;
	}
	obs_post_load_modules();
	auto *scene = obs_scene_create("benchmark");
	std::vector<obs_source_t *> sources;
	for (int i = 0; i < count; ++i) {
		obs_data_t *s = obs_data_create();
		obs_data_set_bool(s, "is_local_file", true);
		obs_data_set_string(s, "local_file", argv[3]);
		obs_data_set_int(s, "width", width);
		obs_data_set_int(s, "height", height);
		obs_data_set_bool(s, "fps_custom", true);
		obs_data_set_int(s, "fps", 60);
		obs_data_set_bool(s, "reroute_audio", true);
		obs_data_set_bool(s, "shutdown", qEnvironmentVariableIsSet("OBS_BROWSER_TEST_SHUTDOWN"));
		auto name = "test-" + std::to_string(i);
		auto *src = obs_source_create("browser_source", name.c_str(), s, nullptr);
		obs_data_release(s);
		if (!src) {
			return 8;
		}
		obs_source_add_audio_capture_callback(src, audio_capture, nullptr);
		obs_scene_add(scene, src);
		sources.push_back(src);
	}
	obs_set_output_source(0, obs_scene_get_source(scene));
	if (qEnvironmentVariableIsSet("OBS_BROWSER_TEST_LIFECYCLE")) {
		auto *item = obs_scene_find_source(scene, "test-0");
		QTimer::singleShot(3000, &app, [item]() { obs_sceneitem_set_visible(item, false); });
		QTimer::singleShot(6000, &app, [item]() { obs_sceneitem_set_visible(item, true); });
		const auto resize = [src = sources[0]](int cx, int cy) {
			obs_data_t *settings = obs_data_create();
			obs_data_set_int(settings, "width", cx);
			obs_data_set_int(settings, "height", cy);
			obs_source_update(src, settings);
			obs_data_release(settings);
		};
		QTimer::singleShot(9000, &app, [resize, width, height]() { resize(width - 160, height - 90); });
		QTimer::singleShot(12000, &app, [resize, width, height]() { resize(width, height); });
	}
	const auto started = os_gettime_ns();
	QTimer capture;
	int frame = 0;
	QObject::connect(&capture, &QTimer::timeout, [&]() {
		obs_enter_graphics();
		auto *render = gs_texrender_create(GS_RGBA, GS_ZS_NONE);
		auto *stage = gs_stagesurface_create(width, height, GS_RGBA);
		if (gs_texrender_begin(render, width, height)) {
			vec4 clear{};
			if (qEnvironmentVariable("OBS_BROWSER_TEST_BACKGROUND") == "white") {
				clear.x = clear.y = clear.z = clear.w = 1.0f;
			} else if (qEnvironmentVariable("OBS_BROWSER_TEST_BACKGROUND") == "black") {
				clear.w = 1.0f;
			}
			gs_clear(GS_CLEAR_COLOR, &clear, 0, 0);
			gs_ortho(0, width, 0, height, -100, 100);
			obs_source_video_render(sources[0]);
			gs_texrender_end(render);
			gs_stage_texture(stage, gs_texrender_get_texture(render));
			uint8_t *pixels = nullptr;
			uint32_t stride = 0;
			if (gs_stagesurface_map(stage, &pixels, &stride)) {
				QImage image(pixels, width, height, stride, QImage::Format_RGBA8888);
				image.save(QString(argv[4]) + QString("/frame-%1.png").arg(frame++));
				gs_stagesurface_unmap(stage);
			}
		}
		gs_stagesurface_destroy(stage);
		gs_texrender_destroy(render);
		obs_leave_graphics();
		printf("METRICS elapsed_s=%.3f fps=%.2f render_ms=%.3f audio_frames=%llu sources=%d\n",
		       (os_gettime_ns() - started) / 1e9, obs_get_active_fps(), obs_get_average_frame_time_ns() / 1e6,
		       (unsigned long long)audio_frames.load(), count);
		for (auto *src : sources) {
			calldata_t data;
			calldata_init(&data);
			if (proc_handler_call(obs_source_get_proc_handler(src), "browser_render_stats", &data)) {
				printf("PAINT source=%s gpu=%lld cpu=%lld fallback=%d elapsed_s=%.3f renders=%lld extra=%lld copy_ns=%lld import_ns=%lld wait_ns=%lld\n",
				       obs_source_get_name(src), (long long)calldata_int(&data, "gpu_frames"),
				       (long long)calldata_int(&data, "cpu_frames"),
				       calldata_bool(&data, "cpu_fallback"), (os_gettime_ns() - started) / 1e9,
				       (long long)calldata_int(&data, "render_frames"),
				       (long long)calldata_int(&data, "extra_copy_frames"),
				       (long long)calldata_int(&data, "gpu_copy_ns"),
				       (long long)calldata_int(&data, "gpu_import_ns"),
				       (long long)calldata_int(&data, "graphics_wait_ns"));
			}
			calldata_free(&data);
		}
		fflush(stdout);
		if (frame == 1 && qEnvironmentVariableIsSet("OBS_BROWSER_TEST_DEVTOOLS")) {
			calldata_t data;
			calldata_init(&data);
			const bool first = proc_handler_call(obs_source_get_proc_handler(sources[0]), "inspect", &data);
			const bool second =
				proc_handler_call(obs_source_get_proc_handler(sources[0]), "inspect", &data);
			calldata_free(&data);
			printf("DEVTOOLS requested=%d\n", first && second);
			fflush(stdout);
		}
	});
	const int capture_ms = qEnvironmentVariableIntValue("OBS_BROWSER_TEST_CAPTURE_INTERVAL_MS");
	capture.start(capture_ms > 0 ? capture_ms : 2300);
	QTimer::singleShot(seconds * 1000, &app, &QApplication::quit);
	app.exec();
	capture.stop();
	obs_set_output_source(0, nullptr);
	for (auto *s : sources) {
		obs_source_remove_audio_capture_callback(s, audio_capture, nullptr);
		obs_source_remove(s);
		obs_source_release(s);
	}
	obs_source_remove(obs_scene_get_source(scene));
	obs_scene_release(scene);
	// Drain source references before unloading CEF.
	do {
		QApplication::sendPostedEvents(nullptr);
	} while (obs_wait_for_destroy_queue());
	QApplication::sendPostedEvents(nullptr);
	obs_shutdown();
	if (wayland) {
		wl_display_disconnect(static_cast<wl_display *>(display));
	} else {
		XCloseDisplay(static_cast<Display *>(display));
	}
	return 0;
}
