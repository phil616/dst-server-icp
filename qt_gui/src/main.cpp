#include "MainWindow.h"

#include <QApplication>
#include <QIcon>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("DST 服务器部署工具"));
    QApplication::setWindowIcon(QIcon(QStringLiteral(":/app/logo-nbg.png")));

    MainWindow window;
    window.show();
    return QApplication::exec();
}
