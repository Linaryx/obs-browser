#include "linux-gpu-policy.hpp"
#include <cstdlib>

#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (false)
int main()
{
	CHECK(ParseLinuxBrowserGPU(nullptr) == LinuxBrowserGPU::Auto);
	CHECK(ParseLinuxBrowserGPU("typo") == LinuxBrowserGPU::Auto);
	CHECK(ParseLinuxBrowserGPU("nvidia") == LinuxBrowserGPU::NVIDIA);
	CHECK(LinuxBrowserCPUPaint(ParseLinuxBrowserGPU("cpu")));
	CHECK(LinuxBrowserCPUPaint(ParseLinuxBrowserGPU("software")));
	CHECK(!LinuxBrowserCPUPaint(ParseLinuxBrowserGPU("auto")));
	CHECK(!LinuxNVIDIAExperimental(LinuxBrowserGPU::NVIDIA, 154, 34, 8037));
	CHECK(!LinuxNVIDIAExperimental(LinuxBrowserGPU::NVIDIA, 156, 1, 8078));
	CHECK(LinuxNVIDIAExperimental(LinuxBrowserGPU::NVIDIA, 156, 3, 8078));
	CHECK(LinuxNVIDIAExperimental(LinuxBrowserGPU::NVIDIA, 156, 14, 8078));
	CHECK(!LinuxNVIDIAExperimental(LinuxBrowserGPU::Auto, 156, 14, 8078));
	CHECK(!LinuxNVIDIAExperimental(LinuxBrowserGPU::CPU, 156, 14, 8078));
	return EXIT_SUCCESS;
}
