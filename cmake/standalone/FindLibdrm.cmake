find_package(PkgConfig REQUIRED)
pkg_check_modules(Libdrm REQUIRED IMPORTED_TARGET libdrm)
add_library(Libdrm::Libdrm ALIAS PkgConfig::Libdrm)
