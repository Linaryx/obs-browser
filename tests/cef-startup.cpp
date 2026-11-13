#include <obs.h>
#include <util/platform.h>
#include <util/threading.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <functional>
#include <iostream>
#include <string>
#include <thread>

namespace {
constexpr const char *kCompleted = "browser startup and immediate shutdown completed";
constexpr const char *kQueueMangled = "_Z12QueueCEFTaskSt8functionIFvvEE";

using InitializeFn = void (*)(void);
using QueueFn = bool (*)(std::function<void()>);

int usage(const char *program)
{
	std::fprintf(stderr, "usage: %s MODULE DATA CONFIG preinit|initialize|source|hold [CEF flags...]\n", program);
	return 2;
}

void *find_symbol(void *library, const char *name)
{
	dlerror();
	void *symbol = dlsym(library, name);
	return dlerror() ? nullptr : symbol;
}

os_event_t *started_event(void *library)
{
	auto **slot = static_cast<os_event_t **>(find_symbol(library, "cef_started_event"));
	return slot ? *slot : nullptr;
}

InitializeFn initialize_function(void *library)
{
	return reinterpret_cast<InitializeFn>(find_symbol(library, "obs_browser_initialize"));
}

int ready_timeout_ms()
{
	const char *value = std::getenv("CEF_STARTUP_READY_TIMEOUT_MS");
	if (!value || !*value) {
		return 30000;
	}
	char *end = nullptr;
	const long parsed = std::strtol(value, &end, 10);
	if (!end || *end || parsed <= 0 || parsed > 600000) {
		return 30000;
	}
	return static_cast<int>(parsed);
}

int run_preinit(void *library)
{
	os_event_t *event = started_event(library);
	if (!event) {
		std::fputs("cef_started_event is not exported by the browser module\n", stderr);
		return 6;
	}
	if (os_event_try(event) == 0) {
		std::fputs("CEF was already initialized before the pre-initialization check\n", stderr);
		return 7;
	}

	auto queue = reinterpret_cast<QueueFn>(find_symbol(library, kQueueMangled));
	if (!queue) {
		queue = reinterpret_cast<QueueFn>(find_symbol(library, "QueueCEFTask"));
	}
	if (!queue) {
		std::fputs("QueueCEFTask is not exported by the browser module\n", stderr);
		return 8;
	}
	if (queue([] {})) {
		std::fputs("task accepted before CEF initialization\n", stderr);
		return 9;
	}
	std::puts("task rejected safely before CEF initialization");
	return 0;
}

int run_initialize(InitializeFn initialize)
{
	initialize();
	return 0;
}

int run_source(void)
{
	obs_source_t *source = obs_source_create_private("browser_source", "startup-audit-source", nullptr);
	if (!source) {
		std::fputs("could not create private browser source\n", stderr);
		return 5;
	}
	obs_source_release(source);
	while (obs_wait_for_destroy_queue()) {
	}
	return 0;
}

int run_hold(InitializeFn initialize, os_event_t *event)
{
	initialize();

	std::atomic<bool> stop{false};
	std::thread ready([event, &stop] {
		const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(ready_timeout_ms());
		while (!stop.load(std::memory_order_relaxed)) {
			if (os_event_timedwait(event, 10) == 0) {
				std::puts("READY");
				std::fflush(stdout);
				return;
			}
			if (std::chrono::steady_clock::now() >= deadline) {
				std::fprintf(stderr, "CEF did not become ready within %d ms\n", ready_timeout_ms());
				return;
			}
		}
	});

	std::string line;
	std::getline(std::cin, line);
	stop.store(true, std::memory_order_relaxed);
	ready.join();
	return 0;
}
} // namespace

int main(int argc, char **argv)
{
	if (argc < 5) {
		return usage(argv[0]);
	}
	const char *mode = argv[4];
	if (std::strcmp(mode, "preinit") != 0 && std::strcmp(mode, "initialize") != 0 &&
	    std::strcmp(mode, "source") != 0 && std::strcmp(mode, "hold") != 0) {
		return usage(argv[0]);
	}

	obs_set_cmdline_args(argc, argv);
	if (!obs_startup("en-US", argv[3], nullptr)) {
		return 3;
	}

	obs_module_t *module = nullptr;
	if (obs_open_module(&module, argv[1], argv[2]) != MODULE_SUCCESS || !obs_init_module(module)) {
		return 4;
	}

	void *library = obs_get_module_lib(module);
	const int result = [&] {
		if (std::strcmp(mode, "preinit") == 0) {
			return run_preinit(library);
		}

		InitializeFn initialize = initialize_function(library);
		if (!initialize) {
			std::fputs("obs_browser_initialize is not exported by the browser module\n", stderr);
			return 6;
		}
		if (std::strcmp(mode, "initialize") == 0) {
			return run_initialize(initialize);
		}
		if (std::strcmp(mode, "source") == 0) {
			return run_source();
		}

		os_event_t *event = started_event(library);
		if (!event) {
			std::fputs("cef_started_event is not exported by the browser module\n", stderr);
			return 6;
		}
		return run_hold(initialize, event);
	}();

	obs_shutdown();
	if (result == 0) {
		std::puts(kCompleted);
		std::fflush(stdout);
	}
	return result;
}
