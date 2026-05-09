cmake_minimum_required(VERSION 3.18)
project(assetkit_blender_native LANGUAGES C)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(ASSETKIT_ROOT "" CACHE PATH "AssetKit source or install root")
set(ASSETKIT_BLENDER_PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assetkit_blender" CACHE PATH "Output directory for the native Python module")
set(ASSETKIT_BLENDER_PYTHON_SOABI "" CACHE STRING "Override Python extension ABI tag, for example cpython-313-darwin")

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

if(NOT ASSETKIT_ROOT AND DEFINED ENV{ASSETKIT_ROOT})
  file(TO_CMAKE_PATH "$ENV{ASSETKIT_ROOT}" ASSETKIT_ROOT_FROM_ENV)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT_FROM_ENV}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(NOT ASSETKIT_ROOT AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assetkit/include/ak/assetkit.h")
  get_filename_component(ASSETKIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../assetkit" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(NOT ASSETKIT_ROOT AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/deps/assetkit/include/ak/assetkit.h")
  get_filename_component(ASSETKIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/deps/assetkit" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

set(ASSETKIT_INCLUDE_HINTS)
set(ASSETKIT_LIBRARY_HINTS)
set(CGLM_INCLUDE_HINTS)
if(ASSETKIT_ROOT)
  list(APPEND ASSETKIT_INCLUDE_HINTS "${ASSETKIT_ROOT}/include")
  list(APPEND CGLM_INCLUDE_HINTS "${ASSETKIT_ROOT}/deps/cglm/include")
  list(APPEND ASSETKIT_LIBRARY_HINTS
    "${ASSETKIT_ROOT}/build"
    "${ASSETKIT_ROOT}/build/src"
    "${ASSETKIT_ROOT}/build/Release"
    "${ASSETKIT_ROOT}/lib")
endif()

find_path(ASSETKIT_INCLUDE_DIR
  NAMES ak/assetkit.h
  HINTS ${ASSETKIT_INCLUDE_HINTS})
find_path(CGLM_INCLUDE_DIR
  NAMES cglm/cglm.h
  HINTS ${CGLM_INCLUDE_HINTS})
find_library(ASSETKIT_LIBRARY
  NAMES assetkit libassetkit
  HINTS ${ASSETKIT_LIBRARY_HINTS})
find_library(ASSETKIT_KTX2_LIBRARY
  NAMES assetkit_ktx2 libassetkit_ktx2
  HINTS ${ASSETKIT_LIBRARY_HINTS})
find_library(ASSETKIT_MESHOPTIMIZER_LIBRARY
  NAMES assetkit_meshoptimizer libassetkit_meshoptimizer
  HINTS ${ASSETKIT_LIBRARY_HINTS})
find_library(ASSETKIT_DRACO_LIBRARY
  NAMES assetkit_draco libassetkit_draco
  HINTS ${ASSETKIT_LIBRARY_HINTS})
find_library(ASSETKIT_SPZ_LIBRARY
  NAMES assetkit_spz libassetkit_spz
  HINTS ${ASSETKIT_LIBRARY_HINTS})

if(NOT ASSETKIT_INCLUDE_DIR)
  message(FATAL_ERROR "AssetKit headers not found. Set ASSETKIT_ROOT.")
endif()
if(NOT ASSETKIT_LIBRARY)
  message(FATAL_ERROR "AssetKit shared library not found. Build AssetKit first or set ASSETKIT_LIBRARY.")
endif()
if(NOT CGLM_INCLUDE_DIR)
  message(FATAL_ERROR "cglm headers not found. Set ASSETKIT_ROOT to an AssetKit source root.")
endif()

Python3_add_library(_assetkit_blender MODULE
  src/native/assetkit_module.c
  src/native/mem.c
  WITH_SOABI)
include(CheckIPOSupported)
check_ipo_supported(RESULT ASSETKIT_BLENDER_IPO_SUPPORTED OUTPUT ASSETKIT_BLENDER_IPO_ERROR)
if(ASSETKIT_BLENDER_IPO_SUPPORTED)
  set_target_properties(_assetkit_blender PROPERTIES INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
endif()
if(ASSETKIT_BLENDER_PYTHON_SOABI)
  string(REGEX REPLACE "^\\." "" ASSETKIT_BLENDER_PYTHON_SOABI_CLEAN "${ASSETKIT_BLENDER_PYTHON_SOABI}")
  set_target_properties(_assetkit_blender PROPERTIES
    SUFFIX ".${ASSETKIT_BLENDER_PYTHON_SOABI_CLEAN}${CMAKE_SHARED_MODULE_SUFFIX}")
endif()
target_include_directories(_assetkit_blender PRIVATE "${ASSETKIT_INCLUDE_DIR}" "${CGLM_INCLUDE_DIR}")
target_compile_definitions(_assetkit_blender PRIVATE CGLM_ALL_UNALIGNED)
target_link_libraries(_assetkit_blender PRIVATE "${ASSETKIT_LIBRARY}")
if(UNIX AND NOT APPLE)
  target_link_libraries(_assetkit_blender PRIVATE m)
endif()
set_target_properties(_assetkit_blender PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${ASSETKIT_BLENDER_PACKAGE_DIR}"
  RUNTIME_OUTPUT_DIRECTORY "${ASSETKIT_BLENDER_PACKAGE_DIR}"
)

get_filename_component(ASSETKIT_LIBRARY_DIR "${ASSETKIT_LIBRARY}" DIRECTORY)
if(APPLE)
  set_target_properties(_assetkit_blender PROPERTIES
    BUILD_WITH_INSTALL_RPATH TRUE
    INSTALL_RPATH "@loader_path;${ASSETKIT_LIBRARY_DIR}"
  )
elseif(UNIX)
  set_target_properties(_assetkit_blender PROPERTIES
    BUILD_WITH_INSTALL_RPATH TRUE
    INSTALL_RPATH "$ORIGIN;${ASSETKIT_LIBRARY_DIR}"
  )
endif()

message(STATUS "AssetKit library: ${ASSETKIT_LIBRARY}")
function(assetkit_blender_copy_decoder decoder_library decoder_label)
  if(NOT decoder_library)
    return()
  endif()
  get_filename_component(ASSETKIT_DECODER_LIBRARY_NAME "${decoder_library}" NAME)
  add_custom_command(TARGET _assetkit_blender POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${decoder_library}"
            "${ASSETKIT_BLENDER_PACKAGE_DIR}/${ASSETKIT_DECODER_LIBRARY_NAME}")
  message(STATUS "AssetKit ${decoder_label} decoder: ${decoder_library}")
endfunction()
assetkit_blender_copy_decoder("${ASSETKIT_KTX2_LIBRARY}" "KTX2")
assetkit_blender_copy_decoder("${ASSETKIT_MESHOPTIMIZER_LIBRARY}" "meshoptimizer")
assetkit_blender_copy_decoder("${ASSETKIT_DRACO_LIBRARY}" "Draco")
assetkit_blender_copy_decoder("${ASSETKIT_SPZ_LIBRARY}" "SPZ")
message(STATUS "Python extension output: ${ASSETKIT_BLENDER_PACKAGE_DIR}")
