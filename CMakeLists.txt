cmake_minimum_required(VERSION 3.18)
project(assetkit_blender_native LANGUAGES C)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(ASSETKIT_ROOT "" CACHE PATH "AssetKit source or install root")
set(ASSETKIT_BLENDER_PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assetkit_blender" CACHE PATH "Output directory for the native Python module")
set(ASSETKIT_BLENDER_PYTHON_SOABI "" CACHE STRING "Override Python extension ABI tag, for example cpython-313-darwin")
option(ASSETKIT_STRICT_ROOT "Only resolve AssetKit headers and libraries from ASSETKIT_ROOT" ON)
option(ASSETKIT_BLENDER_STATIC_ASSETKIT "Link AssetKit core statically into the Python bridge" OFF)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

if(NOT ASSETKIT_ROOT AND DEFINED ENV{ASSETKIT_ROOT})
  file(TO_CMAKE_PATH "$ENV{ASSETKIT_ROOT}" ASSETKIT_ROOT_FROM_ENV)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT_FROM_ENV}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(NOT ASSETKIT_ROOT AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assetio/include/ak/assetkit.h")
  get_filename_component(ASSETKIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../assetio" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(NOT ASSETKIT_ROOT AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/../assetkit/include/ak/assetkit.h")
  get_filename_component(ASSETKIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../assetkit" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(NOT ASSETKIT_ROOT AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/deps/assetkit/include/ak/assetkit.h")
  get_filename_component(ASSETKIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/deps/assetkit" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

if(ASSETKIT_ROOT)
  get_filename_component(ASSETKIT_ROOT "${ASSETKIT_ROOT}" ABSOLUTE)
  set(ASSETKIT_ROOT "${ASSETKIT_ROOT}" CACHE PATH "AssetKit source or install root" FORCE)
endif()

set(ASSETKIT_CACHE_PATH_VARS
  ASSETKIT_INCLUDE_DIR
  CGLM_INCLUDE_DIR
  ASSETKIT_LIBRARY
  ASSETKIT_RUNTIME_LIBRARY
  ASSETKIT_KTX2_LIBRARY
  ASSETKIT_KTX2_RUNTIME_LIBRARY
  ASSETKIT_MESHOPTIMIZER_LIBRARY
  ASSETKIT_MESHOPTIMIZER_RUNTIME_LIBRARY
  ASSETKIT_DRACO_LIBRARY
  ASSETKIT_DRACO_RUNTIME_LIBRARY
  ASSETKIT_SPZ_LIBRARY
  ASSETKIT_SPZ_RUNTIME_LIBRARY
  ASSETKIT_DS_LIBRARY
  ASSETKIT_LIBDEFLATE_LIBRARY
  ASSETKIT_DS_RUNTIME_LIBRARY)

if(ASSETKIT_ROOT AND ASSETKIT_STRICT_ROOT AND DEFINED ASSETKIT_CACHED_ROOT
   AND NOT ASSETKIT_CACHED_ROOT STREQUAL ASSETKIT_ROOT)
  foreach(ASSETKIT_CACHE_VAR IN LISTS ASSETKIT_CACHE_PATH_VARS)
    unset(${ASSETKIT_CACHE_VAR} CACHE)
  endforeach()
endif()

if(ASSETKIT_ROOT AND ASSETKIT_STRICT_ROOT)
  foreach(ASSETKIT_CACHE_VAR IN LISTS ASSETKIT_CACHE_PATH_VARS)
    if(DEFINED ${ASSETKIT_CACHE_VAR}
       AND NOT "${${ASSETKIT_CACHE_VAR}}" MATCHES "-NOTFOUND$")
      get_filename_component(ASSETKIT_CACHED_PATH "${${ASSETKIT_CACHE_VAR}}" ABSOLUTE)
      string(FIND "${ASSETKIT_CACHED_PATH}" "${ASSETKIT_ROOT}/" ASSETKIT_CACHED_PATH_IN_ROOT)
      if(NOT ASSETKIT_CACHED_PATH_IN_ROOT EQUAL 0)
        unset(${ASSETKIT_CACHE_VAR} CACHE)
      endif()
    endif()
  endforeach()
  set(ASSETKIT_CACHED_ROOT "${ASSETKIT_ROOT}" CACHE INTERNAL "AssetKit root used for cached dependency paths")
endif()

set(ASSETKIT_INCLUDE_HINTS)
set(ASSETKIT_LIBRARY_HINTS)
set(CGLM_INCLUDE_HINTS)
set(ASSETKIT_DS_LIBRARY_HINTS)
set(ASSETKIT_LIBDEFLATE_LIBRARY_HINTS)
if(ASSETKIT_ROOT)
  list(APPEND ASSETKIT_INCLUDE_HINTS "${ASSETKIT_ROOT}/include")
  list(APPEND CGLM_INCLUDE_HINTS "${ASSETKIT_ROOT}/deps/cglm/include")
  if(ASSETKIT_BLENDER_STATIC_ASSETKIT)
    list(APPEND ASSETKIT_LIBRARY_HINTS
      "${ASSETKIT_ROOT}/build-static"
      "${ASSETKIT_ROOT}/build-static/src"
      "${ASSETKIT_ROOT}/build-static/Release"
      "${ASSETKIT_ROOT}/build-static/RelWithDebInfo"
      "${ASSETKIT_ROOT}/build-static/Debug"
      "${ASSETKIT_ROOT}/build-static/MinSizeRel")
    list(APPEND ASSETKIT_DS_LIBRARY_HINTS
      "${ASSETKIT_ROOT}/build-static/deps/ds"
      "${ASSETKIT_ROOT}/build-static/deps/ds/Release"
      "${ASSETKIT_ROOT}/build-static/deps/ds/RelWithDebInfo"
      "${ASSETKIT_ROOT}/build-static/deps/ds/Debug"
      "${ASSETKIT_ROOT}/build-static/deps/ds/MinSizeRel")
    list(APPEND ASSETKIT_LIBDEFLATE_LIBRARY_HINTS
      "${ASSETKIT_ROOT}/build-static"
      "${ASSETKIT_ROOT}/build-static/Release"
      "${ASSETKIT_ROOT}/build-static/RelWithDebInfo"
      "${ASSETKIT_ROOT}/build-static/Debug"
      "${ASSETKIT_ROOT}/build-static/MinSizeRel"
      "${ASSETKIT_ROOT}/build-static/deps/libdeflate"
      "${ASSETKIT_ROOT}/build-static/deps/libdeflate/Release"
      "${ASSETKIT_ROOT}/build-static/deps/libdeflate/RelWithDebInfo"
      "${ASSETKIT_ROOT}/build-static/deps/libdeflate/Debug"
      "${ASSETKIT_ROOT}/build-static/deps/libdeflate/MinSizeRel")
  endif()
  list(APPEND ASSETKIT_LIBRARY_HINTS
    "${ASSETKIT_ROOT}/build"
    "${ASSETKIT_ROOT}/build/src"
    "${ASSETKIT_ROOT}/build/Release"
    "${ASSETKIT_ROOT}/build/RelWithDebInfo"
    "${ASSETKIT_ROOT}/build/Debug"
    "${ASSETKIT_ROOT}/build/MinSizeRel"
    "${ASSETKIT_ROOT}/lib")
  list(APPEND ASSETKIT_DS_LIBRARY_HINTS
    "${ASSETKIT_ROOT}/build/deps/ds"
    "${ASSETKIT_ROOT}/build/deps/ds/Release"
    "${ASSETKIT_ROOT}/build/deps/ds/RelWithDebInfo"
    "${ASSETKIT_ROOT}/deps/ds/build"
    "${ASSETKIT_ROOT}/deps/ds/build/Release"
    "${ASSETKIT_ROOT}/deps/ds/build/RelWithDebInfo"
    "${ASSETKIT_ROOT}/lib"
    "${ASSETKIT_ROOT}/bin")
  list(APPEND ASSETKIT_LIBDEFLATE_LIBRARY_HINTS
    "${ASSETKIT_ROOT}/build"
    "${ASSETKIT_ROOT}/build/Release"
    "${ASSETKIT_ROOT}/build/RelWithDebInfo"
    "${ASSETKIT_ROOT}/build/Debug"
    "${ASSETKIT_ROOT}/build/MinSizeRel"
    "${ASSETKIT_ROOT}/build/deps/libdeflate"
    "${ASSETKIT_ROOT}/build/deps/libdeflate/Release"
    "${ASSETKIT_ROOT}/build/deps/libdeflate/RelWithDebInfo"
    "${ASSETKIT_ROOT}/build/deps/libdeflate/Debug"
    "${ASSETKIT_ROOT}/build/deps/libdeflate/MinSizeRel"
    "${ASSETKIT_ROOT}/deps/libdeflate/build"
    "${ASSETKIT_ROOT}/deps/libdeflate/build/Release"
    "${ASSETKIT_ROOT}/deps/libdeflate/build/RelWithDebInfo"
    "${ASSETKIT_ROOT}/deps/libdeflate/build/Debug"
    "${ASSETKIT_ROOT}/deps/libdeflate/build/MinSizeRel"
    "${ASSETKIT_ROOT}/lib")
endif()

set(ASSETKIT_FIND_ROOT_ARGS)
if(ASSETKIT_ROOT AND ASSETKIT_STRICT_ROOT)
  list(APPEND ASSETKIT_FIND_ROOT_ARGS NO_DEFAULT_PATH)
endif()

find_path(ASSETKIT_INCLUDE_DIR
  NAMES ak/assetkit.h
  HINTS ${ASSETKIT_INCLUDE_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_path(CGLM_INCLUDE_DIR
  NAMES cglm/cglm.h
  HINTS ${CGLM_INCLUDE_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_LIBRARY
  NAMES assetkit libassetkit
  HINTS ${ASSETKIT_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_KTX2_LIBRARY
  NAMES assetkit_ktx2 libassetkit_ktx2
  HINTS ${ASSETKIT_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_MESHOPTIMIZER_LIBRARY
  NAMES assetkit_meshoptimizer libassetkit_meshoptimizer
  HINTS ${ASSETKIT_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_DRACO_LIBRARY
  NAMES assetkit_draco libassetkit_draco
  HINTS ${ASSETKIT_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_SPZ_LIBRARY
  NAMES assetkit_spz libassetkit_spz
  HINTS ${ASSETKIT_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_DS_LIBRARY
  NAMES ds libds
  HINTS ${ASSETKIT_DS_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})
find_library(ASSETKIT_LIBDEFLATE_LIBRARY
  NAMES deflatestatic libdeflatestatic deflate libdeflate libdeflate_static
  HINTS ${ASSETKIT_LIBDEFLATE_LIBRARY_HINTS}
  ${ASSETKIT_FIND_ROOT_ARGS})

if(WIN32)
  find_file(ASSETKIT_RUNTIME_LIBRARY
    NAMES assetkit.dll libassetkit.dll
    HINTS ${ASSETKIT_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
  find_file(ASSETKIT_KTX2_RUNTIME_LIBRARY
    NAMES assetkit_ktx2.dll libassetkit_ktx2.dll
    HINTS ${ASSETKIT_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
  find_file(ASSETKIT_MESHOPTIMIZER_RUNTIME_LIBRARY
    NAMES assetkit_meshoptimizer.dll libassetkit_meshoptimizer.dll
    HINTS ${ASSETKIT_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
  find_file(ASSETKIT_DRACO_RUNTIME_LIBRARY
    NAMES assetkit_draco.dll libassetkit_draco.dll
    HINTS ${ASSETKIT_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
  find_file(ASSETKIT_SPZ_RUNTIME_LIBRARY
    NAMES assetkit_spz.dll libassetkit_spz.dll
    HINTS ${ASSETKIT_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
  find_file(ASSETKIT_DS_RUNTIME_LIBRARY
    NAMES ds.dll libds.dll
    HINTS ${ASSETKIT_DS_LIBRARY_HINTS}
    ${ASSETKIT_FIND_ROOT_ARGS})
else()
  set(ASSETKIT_RUNTIME_LIBRARY "${ASSETKIT_LIBRARY}")
  set(ASSETKIT_KTX2_RUNTIME_LIBRARY "${ASSETKIT_KTX2_LIBRARY}")
  set(ASSETKIT_MESHOPTIMIZER_RUNTIME_LIBRARY "${ASSETKIT_MESHOPTIMIZER_LIBRARY}")
  set(ASSETKIT_DRACO_RUNTIME_LIBRARY "${ASSETKIT_DRACO_LIBRARY}")
  set(ASSETKIT_SPZ_RUNTIME_LIBRARY "${ASSETKIT_SPZ_LIBRARY}")
  set(ASSETKIT_DS_RUNTIME_LIBRARY "${ASSETKIT_DS_LIBRARY}")
endif()

if(NOT ASSETKIT_INCLUDE_DIR)
  message(FATAL_ERROR "AssetKit headers not found. Set ASSETKIT_ROOT.")
endif()
if(NOT ASSETKIT_LIBRARY)
  message(FATAL_ERROR "AssetKit library not found. Build AssetKit first or set ASSETKIT_LIBRARY.")
endif()
if(WIN32 AND NOT ASSETKIT_BLENDER_STATIC_ASSETKIT AND NOT ASSETKIT_RUNTIME_LIBRARY)
  message(FATAL_ERROR "AssetKit runtime DLL not found. Build AssetKit first or set ASSETKIT_RUNTIME_LIBRARY.")
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
if(ASSETKIT_BLENDER_STATIC_ASSETKIT)
  target_compile_definitions(_assetkit_blender PRIVATE
    ASSETKIT_BLENDER_STATIC_ASSETKIT=1
    AK_STATIC
    DS_STATIC)
else()
  target_compile_definitions(_assetkit_blender PRIVATE ASSETKIT_BLENDER_STATIC_ASSETKIT=0)
endif()
target_link_libraries(_assetkit_blender PRIVATE "${ASSETKIT_LIBRARY}")
if(ASSETKIT_BLENDER_STATIC_ASSETKIT)
  if(ASSETKIT_DS_LIBRARY)
    target_link_libraries(_assetkit_blender PRIVATE "${ASSETKIT_DS_LIBRARY}")
  endif()
  if(NOT ASSETKIT_LIBDEFLATE_LIBRARY)
    message(FATAL_ERROR
      "AssetKit static libdeflate library not found. "
      "Build AssetKit with AK_STATIC_INTERNAL_DEPS=ON or set ASSETKIT_LIBDEFLATE_LIBRARY.")
  endif()
  target_link_libraries(_assetkit_blender PRIVATE "${ASSETKIT_LIBDEFLATE_LIBRARY}")
endif()
if(UNIX AND NOT APPLE)
  target_link_libraries(_assetkit_blender PRIVATE m ${CMAKE_DL_LIBS})
elseif(APPLE)
  target_link_libraries(_assetkit_blender PRIVATE ${CMAKE_DL_LIBS})
endif()
set_target_properties(_assetkit_blender PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${ASSETKIT_BLENDER_PACKAGE_DIR}"
  RUNTIME_OUTPUT_DIRECTORY "${ASSETKIT_BLENDER_PACKAGE_DIR}"
)
foreach(ASSETKIT_BLENDER_CONFIG DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
  set_target_properties(_assetkit_blender PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY_${ASSETKIT_BLENDER_CONFIG} "${ASSETKIT_BLENDER_PACKAGE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_${ASSETKIT_BLENDER_CONFIG} "${ASSETKIT_BLENDER_PACKAGE_DIR}"
  )
endforeach()

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
if(ASSETKIT_BLENDER_STATIC_ASSETKIT)
  message(STATUS "AssetKit libdeflate library: ${ASSETKIT_LIBDEFLATE_LIBRARY}")
endif()
function(assetkit_blender_copy_runtime_library runtime_library runtime_label)
  if(NOT runtime_library)
    return()
  endif()

  get_filename_component(ASSETKIT_RUNTIME_REALPATH "${runtime_library}" REALPATH)
  get_filename_component(ASSETKIT_RUNTIME_NAME "${runtime_library}" NAME)
  get_filename_component(ASSETKIT_RUNTIME_REALNAME "${ASSETKIT_RUNTIME_REALPATH}" NAME)

  set(ASSETKIT_RUNTIME_OUTPUT_NAMES
    "${ASSETKIT_RUNTIME_NAME}"
    "${ASSETKIT_RUNTIME_REALNAME}")

  if(APPLE AND ASSETKIT_RUNTIME_REALNAME MATCHES "^(.+[^0-9])\\.([0-9]+)(\\.[0-9]+.*)\\.dylib$")
    list(APPEND ASSETKIT_RUNTIME_OUTPUT_NAMES "${CMAKE_MATCH_1}.${CMAKE_MATCH_2}.dylib")
  elseif(UNIX AND ASSETKIT_RUNTIME_REALNAME MATCHES "^(.+[^0-9]\\.so)\\.([0-9]+)(\\..*)$")
    list(APPEND ASSETKIT_RUNTIME_OUTPUT_NAMES "${CMAKE_MATCH_1}.${CMAKE_MATCH_2}")
  endif()

  list(REMOVE_DUPLICATES ASSETKIT_RUNTIME_OUTPUT_NAMES)
  foreach(ASSETKIT_RUNTIME_OUTPUT_NAME IN LISTS ASSETKIT_RUNTIME_OUTPUT_NAMES)
    add_custom_command(TARGET _assetkit_blender POST_BUILD
      COMMAND "${CMAKE_COMMAND}" -E copy_if_different
              "${ASSETKIT_RUNTIME_REALPATH}"
              "${ASSETKIT_BLENDER_PACKAGE_DIR}/${ASSETKIT_RUNTIME_OUTPUT_NAME}")
  endforeach()
  message(STATUS "AssetKit ${runtime_label} runtime: ${runtime_library}")
endfunction()

if(NOT ASSETKIT_BLENDER_STATIC_ASSETKIT)
  assetkit_blender_copy_runtime_library("${ASSETKIT_RUNTIME_LIBRARY}" "core")
  assetkit_blender_copy_runtime_library("${ASSETKIT_DS_RUNTIME_LIBRARY}" "ds")
endif()

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
assetkit_blender_copy_decoder("${ASSETKIT_KTX2_RUNTIME_LIBRARY}" "KTX2")
assetkit_blender_copy_decoder("${ASSETKIT_MESHOPTIMIZER_RUNTIME_LIBRARY}" "meshoptimizer")
assetkit_blender_copy_decoder("${ASSETKIT_DRACO_RUNTIME_LIBRARY}" "Draco")
assetkit_blender_copy_decoder("${ASSETKIT_SPZ_RUNTIME_LIBRARY}" "SPZ")
message(STATUS "Python extension output: ${ASSETKIT_BLENDER_PACKAGE_DIR}")
