cmake_minimum_required(VERSION 3.21)

project(dst_deployer_qt VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)

qt_add_executable(dst-deployer-qt
    src/main.cpp
    src/MainWindow.cpp
    src/MainWindow.h
)

target_link_libraries(dst-deployer-qt PRIVATE Qt6::Widgets)

if(WIN32)
    set_target_properties(dst-deployer-qt PROPERTIES WIN32_EXECUTABLE TRUE)
endif()

