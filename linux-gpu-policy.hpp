#pragma once

#include <string_view>

enum class LinuxBrowserGPU { Auto, NVIDIA, CPU, Software };

inline LinuxBrowserGPU ParseLinuxBrowserGPU(const char *value)
{
	const std::string_view mode = value ? value : "auto";
	if (mode == "nvidia") {
		return LinuxBrowserGPU::NVIDIA;
	}
	if (mode == "cpu") {
		return LinuxBrowserGPU::CPU;
	}
	if (mode == "software") {
		return LinuxBrowserGPU::Software;
	}
	return LinuxBrowserGPU::Auto;
}

inline bool LinuxBrowserCPUPaint(LinuxBrowserGPU mode)
{
	return mode == LinuxBrowserGPU::CPU || mode == LinuxBrowserGPU::Software;
}

inline bool LinuxNVIDIAExperimental(LinuxBrowserGPU mode, int cef_major, int cef_patch, int chromium_build)
{
	// CEF #4238 is present in 156.0.3+ on branch 8078.
	return mode == LinuxBrowserGPU::NVIDIA && chromium_build >= 8078 &&
	       (cef_major > 156 || (cef_major == 156 && cef_patch >= 3));
}
