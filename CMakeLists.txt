cmake_minimum_required(VERSION 3.18)
project(assetkit_blender_native LANGUAGES C)

set(ASSETKIT_ROOT "" CACHE PATH "AssetKit source or install root")
set(ASSETKIT_BLENDER_PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assetkit_blender" CACHE PATH "Output directory for the native Python module")

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
if(ASSETKIT_ROOT)
  list(APPEND ASSETKIT_INCLUDE_HINTS "${ASSETKIT_ROOT}/include")
  list(APPEND ASSETKIT_LIBRARY_HINTS
    "${ASSETKIT_ROOT}/build"
    "${ASSETKIT_ROOT}/build/src"
    "${ASSETKIT_ROOT}/build/Release"
    "${ASSETKIT_ROOT}/lib")
endif()

find_path(ASSETKIT_INCLUDE_DIR
  NAMES ak/assetkit.h
  HINTS ${ASSETKIT_INCLUDE_HINTS})
find_library(ASSETKIT_LIBRARY
  NAMES assetkit libassetkit
  HINTS ${ASSETKIT_LIBRARY_HINTS})

if(NOT ASSETKIT_INCLUDE_DIR)
  message(FATAL_ERROR "AssetKit headers not found. Set ASSETKIT_ROOT.")
endif()
if(NOT ASSETKIT_LIBRARY)
  message(FATAL_ERROR "AssetKit shared library not found. Build AssetKit first or set ASSETKIT_LIBRARY.")
endif()

Python3_add_library(_assetkit_blender MODULE src/native/assetkit_module.c WITH_SOABI)
target_include_directories(_assetkit_blender PRIVATE "${ASSETKIT_INCLUDE_DIR}")
target_link_libraries(_assetkit_blender PRIVATE "${ASSETKIT_LIBRARY}")
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
message(STATUS "Python extension output: ${ASSETKIT_BLENDER_PACKAGE_DIR}")
