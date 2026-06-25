cmake_minimum_required(VERSION 3.20)

project(pps_3dti_renderer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(THREEDTI_ROOT "${CMAKE_CURRENT_LIST_DIR}/../3dti_AudioToolkit" CACHE PATH "Pinned 3DTI AudioToolkit source root")
set(NLOHMANN_JSON_ROOT "${CMAKE_CURRENT_LIST_DIR}/../nlohmann_json" CACHE PATH "Pinned nlohmann/json source root")
set(SOFA_BUNDLED_ROOT "${THREEDTI_ROOT}/3dti_ResourceManager/third_party_libraries/sofacoustics/libsofa" CACHE PATH "Bundled SOFA C++ API root from 3DTI's pinned submodule")
set(SOFA_INCLUDE_DIR "" CACHE PATH "Directory containing SOFA.h from the SOFA C++ reader used by 3DTI")
set(SOFA_LIBRARY "" CACHE FILEPATH "SOFA C++ reader library used by 3DTI")
option(PPS_ENABLE_SOFA_READER "Enable 3DTI SOFA-file loading through the external SOFA C++ reader" ON)
option(PPS_USE_BUNDLED_SOFA_READER "Build the SOFA C++ reader from 3DTI's pinned bundled submodule when no external SOFA library is provided" ON)

if(NOT EXISTS "${THREEDTI_ROOT}/3dti_Toolkit/BinauralSpatializer/Core.h")
  message(FATAL_ERROR "THREEDTI_ROOT does not point at the pinned 3DTI source snapshot: ${THREEDTI_ROOT}")
endif()

if(NOT EXISTS "${NLOHMANN_JSON_ROOT}/single_include/nlohmann/json.hpp")
  message(FATAL_ERROR "NLOHMANN_JSON_ROOT does not point at the pinned nlohmann/json single-header snapshot: ${NLOHMANN_JSON_ROOT}")
endif()

if(PPS_ENABLE_SOFA_READER)
  if(SOFA_INCLUDE_DIR AND SOFA_LIBRARY)
    if(NOT EXISTS "${SOFA_INCLUDE_DIR}/SOFA.h")
      message(FATAL_ERROR "SOFA_INCLUDE_DIR does not contain SOFA.h: ${SOFA_INCLUDE_DIR}")
    endif()
    if(NOT EXISTS "${SOFA_LIBRARY}")
      message(FATAL_ERROR "SOFA_LIBRARY was set but does not exist: ${SOFA_LIBRARY}")
    endif()
  elseif(PPS_USE_BUNDLED_SOFA_READER AND EXISTS "${SOFA_BUNDLED_ROOT}/src/SOFA.h")
    set(SOFA_INCLUDE_DIR "${SOFA_BUNDLED_ROOT}/src")
    set(SOFA_DEPENDENCY_INCLUDE_DIR "${SOFA_BUNDLED_ROOT}/dependencies/include")
    set(SOFA_WINDOWS_LIB_DIR "${SOFA_BUNDLED_ROOT}/dependencies/lib/win")
    set(SOFA_WINDOWS_DLL_DIR "${SOFA_BUNDLED_ROOT}/dependencies/lib/win/x64")

    file(GLOB PPS_SOFA_API_SOURCES CONFIGURE_DEPENDS
      "${SOFA_BUNDLED_ROOT}/src/SOFA*.cpp"
    )
    list(REMOVE_ITEM PPS_SOFA_API_SOURCES
      "${SOFA_BUNDLED_ROOT}/src/json2sofa.cpp"
      "${SOFA_BUNDLED_ROOT}/src/sofa2json.cpp"
      "${SOFA_BUNDLED_ROOT}/src/sofaexamples.cpp"
      "${SOFA_BUNDLED_ROOT}/src/sofainfo.cpp"
      "${SOFA_BUNDLED_ROOT}/src/sofamisc.cpp"
    )
    file(GLOB PPS_SOFA_NETCDF_CXX_SOURCES CONFIGURE_DEPENDS
      "${SOFA_DEPENDENCY_INCLUDE_DIR}/nc*.cpp"
    )

    add_library(pps-bundled-sofa STATIC
      ${PPS_SOFA_API_SOURCES}
      ${PPS_SOFA_NETCDF_CXX_SOURCES}
    )
    target_compile_definitions(pps-bundled-sofa PUBLIC NOMINMAX)
    target_include_directories(pps-bundled-sofa PUBLIC
      "${SOFA_INCLUDE_DIR}"
      "${SOFA_DEPENDENCY_INCLUDE_DIR}"
    )
    target_link_libraries(pps-bundled-sofa PUBLIC
      "${SOFA_WINDOWS_LIB_DIR}/netcdf_x64.lib"
      "${SOFA_WINDOWS_LIB_DIR}/libhdf5_x64.lib"
      "${SOFA_WINDOWS_LIB_DIR}/libhdf5_hl_x64.lib"
      "${SOFA_WINDOWS_LIB_DIR}/libcurl_imp_x64.lib"
      "${SOFA_WINDOWS_LIB_DIR}/zlib_x64.lib"
    )
    set(PPS_BUNDLED_SOFA_RUNTIME_DLLS
      "${SOFA_WINDOWS_DLL_DIR}/netcdf.dll"
      "${SOFA_WINDOWS_DLL_DIR}/hdf5.dll"
      "${SOFA_WINDOWS_DLL_DIR}/hdf5_hl.dll"
      "${SOFA_WINDOWS_DLL_DIR}/libcurl.dll"
      "${SOFA_WINDOWS_DLL_DIR}/zlib1.dll"
    )
  else()
    message(FATAL_ERROR "Set SOFA_INCLUDE_DIR/SOFA_LIBRARY, vendor the SOFA submodule, or configure with -DPPS_ENABLE_SOFA_READER=OFF to require a preconverted .3dti-hrtf cache.")
  endif()
endif()

file(GLOB THREEDTI_COMMON_SOURCES CONFIGURE_DEPENDS
  "${THREEDTI_ROOT}/3dti_Toolkit/Common/*.cpp"
)
list(REMOVE_ITEM THREEDTI_COMMON_SOURCES
  "${THREEDTI_ROOT}/3dti_Toolkit/Common/Profiler.cpp"
)
file(GLOB THREEDTI_BINAURAL_SOURCES CONFIGURE_DEPENDS
  "${THREEDTI_ROOT}/3dti_Toolkit/BinauralSpatializer/*.cpp"
)
file(GLOB THREEDTI_HAHL_SOURCES CONFIGURE_DEPENDS
  "${THREEDTI_ROOT}/3dti_Toolkit/HAHLSimulation/*.cpp"
)
set(THREEDTI_HRTF_RESOURCE_SOURCES
  "${THREEDTI_ROOT}/3dti_ResourceManager/HRTF/HRTFCereal.cpp"
)
if(PPS_ENABLE_SOFA_READER)
  list(APPEND THREEDTI_HRTF_RESOURCE_SOURCES
    "${THREEDTI_ROOT}/3dti_ResourceManager/HRTF/HRTFFactory.cpp"
  )
endif()
file(GLOB THREEDTI_ILD_RESOURCE_SOURCES CONFIGURE_DEPENDS
  "${THREEDTI_ROOT}/3dti_ResourceManager/ILD/*.cpp"
)

add_executable(pps-3dti-renderer
  src/pps_3dti_renderer.cpp
  ${THREEDTI_COMMON_SOURCES}
  ${THREEDTI_BINAURAL_SOURCES}
  ${THREEDTI_HAHL_SOURCES}
  ${THREEDTI_HRTF_RESOURCE_SOURCES}
  ${THREEDTI_ILD_RESOURCE_SOURCES}
)

target_compile_definitions(pps-3dti-renderer PRIVATE
  _3DTI_ANGLE_CONVENTION_DEFAULT
  NOMINMAX
)

target_include_directories(pps-3dti-renderer PRIVATE
  "${THREEDTI_ROOT}/3dti_Toolkit"
  "${THREEDTI_ROOT}/3dti_ResourceManager"
  "${THREEDTI_ROOT}/3dti_ResourceManager/third_party_libraries/boost_circular_buffer"
  "${THREEDTI_ROOT}/3dti_ResourceManager/third_party_libraries/cereal/include"
  "${THREEDTI_ROOT}/3dti_ResourceManager/third_party_libraries/eigen"
  "${NLOHMANN_JSON_ROOT}/single_include"
)

if(PPS_ENABLE_SOFA_READER)
  target_compile_definitions(pps-3dti-renderer PRIVATE PPS_ENABLE_SOFA_READER=1)
  target_include_directories(pps-3dti-renderer PRIVATE "${SOFA_INCLUDE_DIR}")
  if(TARGET pps-bundled-sofa)
    target_link_libraries(pps-3dti-renderer PRIVATE pps-bundled-sofa)
    foreach(PPS_RUNTIME_DLL IN LISTS PPS_BUNDLED_SOFA_RUNTIME_DLLS)
      add_custom_command(TARGET pps-3dti-renderer POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${PPS_RUNTIME_DLL}"
          "$<TARGET_FILE_DIR:pps-3dti-renderer>"
      )
    endforeach()
  else()
    target_link_libraries(pps-3dti-renderer PRIVATE "${SOFA_LIBRARY}")
  endif()
endif()

set_target_properties(pps-3dti-renderer PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/bin"
)
