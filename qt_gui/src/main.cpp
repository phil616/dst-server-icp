#include "MainWindow.h"

#include <QApplication>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("DST 服务器部署工具"));

    MainWindow window;
    window.show();
    return QApplication::exec();
}

