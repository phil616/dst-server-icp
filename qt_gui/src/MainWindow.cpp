#include "MainWindow.h"

#include <QApplication>
#include <QCheckBox>
#include <QComboBox>
#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFileInfo>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QSignalBlocker>
#include <QStandardPaths>
#include <QTabWidget>
#include <QTextCursor>
#include <QUrl>
#include <QVBoxLayout>

#include <stdexcept>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent), corePath_(locateCore())
{
    setWindowTitle(QStringLiteral("DST 服务器部署工具"));
    resize(980, 680);
    applyStyle();

    auto *root = new QWidget(this);
    auto *outer = new QVBoxLayout(root);
    outer->setContentsMargins(18, 16, 18, 14);
    outer->setSpacing(12);

    auto *titleRow = new QHBoxLayout();
    auto *title = new QLabel(QStringLiteral("DST 服务器部署工具"), root);
    title->setObjectName(QStringLiteral("Title"));
    auto *subtitle = new QLabel(QStringLiteral("C++ Qt 版部署助手"), root);
    subtitle->setObjectName(QStringLiteral("Subtitle"));
    titleRow->addWidget(title);
    titleRow->addWidget(subtitle);
    titleRow->addStretch(1);
    outer->addLayout(titleRow);

    tabs_ = new QTabWidget(root);
    tabs_->addTab(buildDeployTab(), QStringLiteral("部署"));
    tabs_->addTab(buildFirewallTab(), QStringLiteral("开放端口"));
    tabs_->addTab(buildSettingsTab(), QStringLiteral("设置"));
    tabs_->addTab(buildHelpTab(), QStringLiteral("帮助"));
    outer->addWidget(tabs_, 1);

    auto *bottom = new QHBoxLayout();
    statusLabel_ = new QLabel(QStringLiteral("● 空闲"), root);
    auto *helpBtn = new QPushButton(QStringLiteral("使用帮助"), root);
    connect(helpBtn, &QPushButton::clicked, this, [this]() { tabs_->setCurrentIndex(3); });
    bottom->addWidget(statusLabel_, 1);
    bottom->addWidget(helpBtn);
    outer->addLayout(bottom);

    setCentralWidget(root);
    loadConfig();
}

QWidget *MainWindow::buildDeployTab()
{
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    layout->setSpacing(12);

    auto *profileBox = new QGroupBox(QStringLiteral("连接信息"), page);
    auto *form = new QFormLayout(profileBox);
    form->setLabelAlignment(Qt::AlignRight);

    auto *profileRow = new QHBoxLayout();
    profileSelect_ = new QComboBox(profileBox);
    saveBtn_ = new QPushButton(QStringLiteral("保存"), profileBox);
    deleteBtn_ = new QPushButton(QStringLiteral("删除"), profileBox);
    profileRow->addWidget(profileSelect_, 1);
    profileRow->addWidget(saveBtn_);
    profileRow->addWidget(deleteBtn_);
    form->addRow(QStringLiteral("连接"), profileRow);
    connect(profileSelect_, &QComboBox::currentIndexChanged, this, &MainWindow::selectProfile);
    connect(saveBtn_, &QPushButton::clicked, this, &MainWindow::saveProfile);
    connect(deleteBtn_, &QPushButton::clicked, this, &MainWindow::deleteProfile);

    nameEntry_ = new QLineEdit(profileBox);
    nameEntry_->setPlaceholderText(QStringLiteral("配置名称,如:阿里云服务器-A"));
    form->addRow(QStringLiteral("命名"), nameEntry_);

    auto *hostRow = new QHBoxLayout();
    hostEntry_ = new QLineEdit(profileBox);
    hostEntry_->setPlaceholderText(QStringLiteral("主机 IP 或域名"));
    portEntry_ = new QLineEdit(QStringLiteral("22"), profileBox);
    portEntry_->setMaximumWidth(120);
    hostRow->addWidget(hostEntry_, 1);
    hostRow->addWidget(new QLabel(QStringLiteral("端口"), profileBox));
    hostRow->addWidget(portEntry_);
    form->addRow(QStringLiteral("主机"), hostRow);

    auto *userRow = new QHBoxLayout();
    userEntry_ = new QLineEdit(profileBox);
    userEntry_->setPlaceholderText(QStringLiteral("登录用户,如:root"));
    passEntry_ = new QLineEdit(profileBox);
    passEntry_->setEchoMode(QLineEdit::Password);
    passEntry_->setPlaceholderText(QStringLiteral("登录密码"));
    userRow->addWidget(userEntry_);
    userRow->addWidget(passEntry_);
    form->addRow(QStringLiteral("用户 / 密码"), userRow);
    layout->addWidget(profileBox);

    auto *actions = new QGroupBox(QStringLiteral("部署操作"), page);
    auto *grid = new QGridLayout(actions);
    testBtn_ = actionButton(QStringLiteral("① 测试连接"), QStringLiteral("test"));
    aptBtn_ = actionButton(QStringLiteral("② 系统准备"), QStringLiteral("apt"));
    statusBtn_ = actionButton(QStringLiteral("查看服务状态"), QStringLiteral("status"));
    installBtn_ = actionButton(QStringLiteral("③ 安装管理器"), QStringLiteral("install"), true);
    updateBtn_ = actionButton(QStringLiteral("升级管理器"), QStringLiteral("update"));
    uninstallBtn_ = actionButton(QStringLiteral("卸载管理器"), QStringLiteral("uninstall"), false, true);
    QList<QPushButton *> buttons{testBtn_, aptBtn_, statusBtn_, installBtn_, updateBtn_, uninstallBtn_};
    for (int i = 0; i < buttons.size(); ++i) {
        grid->addWidget(buttons[i], i / 3, i % 3);
    }
    layout->addWidget(actions);

    auto *logBox = new QGroupBox(QStringLiteral("运行日志"), page);
    auto *logLayout = new QVBoxLayout(logBox);
    auto *logTools = new QHBoxLayout();
    cancelBtn_ = new QPushButton(QStringLiteral("取消"), logBox);
    cancelBtn_->setEnabled(false);
    auto *clearBtn = new QPushButton(QStringLiteral("清空日志"), logBox);
    auto *openLogBtn = new QPushButton(QStringLiteral("日志目录"), logBox);
    auto *openConfigBtn = new QPushButton(QStringLiteral("持久化目录"), logBox);
    logTools->addWidget(cancelBtn_);
    logTools->addWidget(clearBtn);
    logTools->addWidget(openLogBtn);
    logTools->addWidget(openConfigBtn);
    logTools->addStretch(1);
    connect(cancelBtn_, &QPushButton::clicked, this, &MainWindow::cancelOperation);
    connect(clearBtn, &QPushButton::clicked, this, [this]() { logView_->clear(); });
    connect(openLogBtn, &QPushButton::clicked, this, &MainWindow::openLogDir);
    connect(openConfigBtn, &QPushButton::clicked, this, &MainWindow::openConfigDir);
    logView_ = new QPlainTextEdit(logBox);
    logView_->setReadOnly(true);
    logView_->setMaximumBlockCount(1500);
    logView_->setObjectName(QStringLiteral("LogView"));
    logLayout->addLayout(logTools);
    logLayout->addWidget(logView_, 1);
    layout->addWidget(logBox, 1);
    return page;
}

QWidget *MainWindow::buildFirewallTab()
{
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    layout->setSpacing(12);

    auto *notice = new QLabel(QStringLiteral("这里操作的是服务器系统防火墙,不是云服务商安全组。两者都放行后外网才连得上。"), page);
    notice->setObjectName(QStringLiteral("Notice"));
    notice->setWordWrap(true);
    layout->addWidget(notice);

    fwStatusLabel_ = new QLabel(QStringLiteral("尚未检测,请先点“检测防火墙”"), page);
    fwStatusLabel_->setObjectName(QStringLiteral("StatusText"));
    fwStatusLabel_->setWordWrap(true);
    layout->addWidget(fwStatusLabel_);

    fwDetectBtn_ = new QPushButton(QStringLiteral("① 检测防火墙"), page);
    fwDetectBtn_->setProperty("primary", true);
    connect(fwDetectBtn_, &QPushButton::clicked, this, [this]() { runOperation(QStringLiteral("detect-firewall")); });
    layout->addWidget(fwDetectBtn_);

    auto *box = new QGroupBox(QStringLiteral("放行端口"), page);
    auto *form = new QFormLayout(box);
    fwPortEntry_ = new QLineEdit(QStringLiteral("8000"), box);
    fwProtoSelect_ = new QComboBox(box);
    fwProtoSelect_->addItems({QStringLiteral("TCP + UDP(推荐)"), QStringLiteral("仅 TCP"), QStringLiteral("仅 UDP")});
    fwAllowBtn_ = new QPushButton(QStringLiteral("② 放行此端口"), box);
    fwAllowBtn_->setProperty("primary", true);
    connect(fwAllowBtn_, &QPushButton::clicked, this, [this]() { runOperation(QStringLiteral("allow-port")); });
    form->addRow(QStringLiteral("端口"), fwPortEntry_);
    form->addRow(QStringLiteral("协议"), fwProtoSelect_);
    form->addRow(QString(), fwAllowBtn_);
    layout->addWidget(box);

    fwDisableBtn_ = new QPushButton(QStringLiteral("关闭系统防火墙"), page);
    fwDisableBtn_->setProperty("danger", true);
    connect(fwDisableBtn_, &QPushButton::clicked, this, [this]() {
        auto ok = QMessageBox::question(this, QStringLiteral("确认关闭系统防火墙"),
            QStringLiteral("关闭后服务器将不再有系统层防护,所有端口对外开放(仍受云安全组限制)。确定关闭?"));
        if (ok == QMessageBox::Yes) {
            runOperation(QStringLiteral("disable-firewall"));
        }
    });
    layout->addWidget(fwDisableBtn_);
    layout->addStretch(1);
    return page;
}

QWidget *MainWindow::buildSettingsTab()
{
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    auto *box = new QGroupBox(QStringLiteral("部署偏好"), page);
    auto *form = new QFormLayout(box);
    mirrorEntry_ = new QLineEdit(box);
    mirrorEntry_->setPlaceholderText(QStringLiteral("https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"));
    sudoCheck_ = new QCheckBox(QStringLiteral("非 root 用户用 sudo 提权"), box);
    upgradeCheck_ = new QCheckBox(QStringLiteral("系统准备时顺带 apt upgrade"), box);
    form->addRow(QStringLiteral("PyPI 镜像"), mirrorEntry_);
    form->addRow(QString(), sudoCheck_);
    form->addRow(QString(), upgradeCheck_);
    layout->addWidget(box);
    layout->addStretch(1);
    return page;
}

QWidget *MainWindow::buildHelpTab()
{
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    auto *content = new QWidget(scroll);
    auto *layout = new QVBoxLayout(content);
    QStringList texts{
        QStringLiteral("饥荒(DST)服务器一键部署助手"),
        QStringLiteral("填写 SSH 连接信息后,依次执行测试连接、系统准备、安装管理器。安装完成后浏览器打开 http://服务器IP:8000/ 进入 Web 管理端。"),
        QStringLiteral("升级管理器会保留游戏、存档与数据库。卸载管理器会删除服务和源码,保留游戏存档与缓存。"),
        QStringLiteral("系统防火墙和云服务商安全组相互独立。游戏端口和管理面板端口需要两边都放行。"),
    };
    for (const auto &text : texts) {
        auto *label = new QLabel(text, content);
        label->setWordWrap(true);
        if (text.startsWith(QStringLiteral("饥荒"))) {
            label->setObjectName(QStringLiteral("HelpTitle"));
        }
        layout->addWidget(label);
    }
    layout->addStretch(1);
    scroll->setWidget(content);
    return scroll;
}

QPushButton *MainWindow::actionButton(const QString &text, const QString &operation, bool primary, bool danger)
{
    auto *button = new QPushButton(text, this);
    button->setMinimumHeight(40);
    button->setProperty("primary", primary);
    button->setProperty("danger", danger);
    connect(button, &QPushButton::clicked, this, [this, operation]() {
        if (operation == QStringLiteral("uninstall")) {
            auto ok = QMessageBox::question(this, QStringLiteral("确认卸载"),
                QStringLiteral("将删除管理器源码与服务(保留游戏存档与数据库)。确定继续?"));
            if (ok != QMessageBox::Yes) {
                return;
            }
        }
        runOperation(operation);
    });
    return button;
}

QString MainWindow::locateCore() const
{
    const QString overridePath = qEnvironmentVariable("DST_DEPLOYER_CORE");
    if (!overridePath.isEmpty()) {
        return overridePath;
    }
#ifdef Q_OS_WIN
    const QString exe = QStringLiteral("dst-deployer-core.exe");
#else
    const QString exe = QStringLiteral("dst-deployer-core");
#endif
    QStringList candidates{
        QDir(QCoreApplication::applicationDirPath()).filePath(exe),
        QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("../gui/dist/%1").arg(exe)),
        QDir::current().filePath(QStringLiteral("../gui/dist/%1").arg(exe)),
        QDir::current().filePath(QStringLiteral("gui/dist/%1").arg(exe)),
    };
    for (const auto &path : candidates) {
        if (QFileInfo::exists(path)) {
            return QFileInfo(path).absoluteFilePath();
        }
    }
    return candidates.first();
}

void MainWindow::loadConfig()
{
    if (!QFileInfo::exists(corePath_)) {
        setStatus(QStringLiteral("fail"), QStringLiteral("未找到 core: %1").arg(corePath_));
        return;
    }
    loadPaths();
    QJsonObject event;
    try {
        event = callCore(QStringLiteral("config"));
    } catch (const std::exception &ex) {
        setStatus(QStringLiteral("fail"), QStringLiteral("读取配置失败"));
        showError(QStringLiteral("%1\n\n可点击“持久化目录”打开配置目录,删除 config.json 后重试。").arg(QString::fromUtf8(ex.what())));
        return;
    }
    if (!event.contains(QStringLiteral("config"))) {
        setStatus(QStringLiteral("fail"), QStringLiteral("读取配置失败: core 未返回配置"));
        return;
    }
    const auto payload = event.value(QStringLiteral("config")).toObject();
    const auto cfg = payload.value(QStringLiteral("config")).toObject();
    configPath_ = payload.value(QStringLiteral("path")).toString();
    logDir_ = payload.value(QStringLiteral("log_dir")).toString();
    mirrorEntry_->setText(cfg.value(QStringLiteral("mirror")).toString(payload.value(QStringLiteral("default_mirror")).toString()));
    sudoCheck_->setChecked(cfg.value(QStringLiteral("use_sudo")).toBool(true));
    upgradeCheck_->setChecked(cfg.value(QStringLiteral("apt_upgrade")).toBool(false));
    profiles_.clear();
    for (const auto &item : cfg.value(QStringLiteral("profiles")).toArray()) {
        profiles_.append(item.toObject());
    }
    refreshProfiles(cfg.value(QStringLiteral("selected")).toString());
    setStatus(QStringLiteral("idle"), QStringLiteral("● 空闲"));
}

void MainWindow::loadPaths()
{
    try {
        const auto event = callCore(QStringLiteral("paths"));
        const auto payload = event.value(QStringLiteral("config")).toObject();
        const QString path = payload.value(QStringLiteral("path")).toString();
        const QString logs = payload.value(QStringLiteral("log_dir")).toString();
        if (!path.isEmpty()) {
            configPath_ = path;
        }
        if (!logs.isEmpty()) {
            logDir_ = logs;
        }
    } catch (const std::exception &) {
        // loadConfig will surface the main error. This best-effort path lookup
        // only exists so users can recover from a broken config file.
    }
}

void MainWindow::refreshProfiles(const QString &selected)
{
    QSignalBlocker blocker(profileSelect_);
    profileSelect_->clear();
    profileSelect_->addItem(QStringLiteral("（选择已保存的连接）"));
    for (const auto &profile : profiles_) {
        profileSelect_->addItem(profile.value(QStringLiteral("name")).toString(), profile);
    }
    int index = 0;
    for (int i = 1; i < profileSelect_->count(); ++i) {
        if (profileSelect_->itemText(i) == selected) {
            index = i;
            break;
        }
    }
    profileSelect_->setCurrentIndex(index);
    if (index > 0) {
        fillProfile(profileSelect_->itemData(index).toJsonObject());
    }
}

void MainWindow::selectProfile(int index)
{
    if (index > 0) {
        fillProfile(profileSelect_->itemData(index).toJsonObject());
    }
}

void MainWindow::fillProfile(const QJsonObject &profile)
{
    nameEntry_->setText(profile.value(QStringLiteral("name")).toString());
    hostEntry_->setText(profile.value(QStringLiteral("host")).toString());
    portEntry_->setText(QString::number(profile.value(QStringLiteral("port")).toInt(22)));
    userEntry_->setText(profile.value(QStringLiteral("user")).toString());
    passEntry_->setText(profile.value(QStringLiteral("password")).toString());
}

QJsonObject MainWindow::profileFromForm() const
{
    const QString host = hostEntry_->text().trimmed();
    const QString user = userEntry_->text().trimmed();
    bool ok = false;
    const int port = portEntry_->text().trimmed().toInt(&ok);
    if (host.isEmpty()) {
        throw std::runtime_error("主机不能为空");
    }
    if (user.isEmpty()) {
        throw std::runtime_error("用户不能为空");
    }
    if (!ok || port <= 0 || port > 65535) {
        throw std::runtime_error("端口必须是 1-65535 的整数");
    }
    QString name = nameEntry_->text().trimmed();
    if (name.isEmpty()) {
        name = QStringLiteral("%1@%2").arg(user, host);
    }
    return {
        {QStringLiteral("name"), name},
        {QStringLiteral("host"), host},
        {QStringLiteral("port"), port},
        {QStringLiteral("user"), user},
        {QStringLiteral("password"), passEntry_->text()},
    };
}

QJsonObject MainWindow::baseRequest() const
{
    const auto profile = profileFromForm();
    return {
        {QStringLiteral("profile"), profile},
        {QStringLiteral("selected"), profile.value(QStringLiteral("name")).toString()},
        {QStringLiteral("mirror"), mirrorEntry_->text().trimmed()},
        {QStringLiteral("use_sudo"), sudoCheck_->isChecked()},
        {QStringLiteral("apt_upgrade"), upgradeCheck_->isChecked()},
    };
}

QJsonObject MainWindow::runRequest(const QString &operation) const
{
    const auto profile = profileFromForm();
    return {
        {QStringLiteral("operation"), operation},
        {QStringLiteral("profile"), profile},
        {QStringLiteral("mirror"), mirrorEntry_->text().trimmed()},
        {QStringLiteral("use_sudo"), sudoCheck_->isChecked()},
        {QStringLiteral("apt_upgrade"), upgradeCheck_->isChecked()},
    };
}

void MainWindow::saveProfile()
{
    try {
        const auto req = baseRequest();
        callCore(QStringLiteral("save-profile"), req);
        appendLog(QStringLiteral("已保存连接:%1").arg(req.value(QStringLiteral("selected")).toString()));
        loadConfig();
    } catch (const std::exception &ex) {
        showError(QString::fromUtf8(ex.what()));
    }
}

void MainWindow::deleteProfile()
{
    const QString name = nameEntry_->text().trimmed();
    if (name.isEmpty()) {
        return;
    }
    auto ok = QMessageBox::question(this, QStringLiteral("确认删除"), QStringLiteral("删除已保存连接「%1」?").arg(name));
    if (ok != QMessageBox::Yes) {
        return;
    }
    try {
        callCore(QStringLiteral("delete-profile"), {{QStringLiteral("name"), name}});
        appendLog(QStringLiteral("已删除连接:%1").arg(name));
        loadConfig();
    } catch (const std::exception &ex) {
        showError(QString::fromUtf8(ex.what()));
    }
}

QJsonObject MainWindow::callCore(const QString &command, const QJsonObject &payload) const
{
    QProcess proc;
    proc.setProgram(corePath_);
    proc.setArguments({command});
    proc.start();
    if (!proc.waitForStarted(3000)) {
        throw std::runtime_error("启动 core 失败");
    }
    if (!payload.isEmpty()) {
        proc.write(QJsonDocument(payload).toJson(QJsonDocument::Compact));
    }
    proc.closeWriteChannel();
    proc.waitForFinished(-1);
    const auto events = parseJsonLines(proc.readAllStandardOutput());
    if (proc.exitCode() != 0) {
        for (const auto &event : events) {
            if (event.value(QStringLiteral("type")).toString() == QStringLiteral("error")) {
                throw std::runtime_error(event.value(QStringLiteral("message")).toString().toStdString());
            }
        }
        throw std::runtime_error(proc.readAllStandardError().toStdString());
    }
    return events.isEmpty() ? QJsonObject{} : events.first();
}

QList<QJsonObject> MainWindow::parseJsonLines(const QByteArray &data) const
{
    QList<QJsonObject> out;
    for (const auto &line : data.split('\n')) {
        if (line.trimmed().isEmpty()) {
            continue;
        }
        QJsonParseError parseError;
        const auto doc = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error == QJsonParseError::NoError && doc.isObject()) {
            out.append(doc.object());
        } else {
            out.append({{QStringLiteral("type"), QStringLiteral("log")}, {QStringLiteral("line"), QString::fromUtf8(line)}});
        }
    }
    return out;
}

void MainWindow::runOperation(const QString &operation)
{
    if (coreProcess_) {
        appendLog(QStringLiteral("已有操作在进行,请先等待或取消"));
        return;
    }
    try {
        const auto saveReq = baseRequest();
        auto req = runRequest(operation);
        if (operation == QStringLiteral("allow-port")) {
            const auto protos = protoFlags();
            req.insert(QStringLiteral("port"), firewallPort());
            req.insert(QStringLiteral("tcp"), protos.first);
            req.insert(QStringLiteral("udp"), protos.second);
        }
        callCore(QStringLiteral("save-profile"), saveReq);

        coreProcess_ = new QProcess(this);
        processBuffer_.clear();
        coreProcess_->setProgram(corePath_);
        coreProcess_->setArguments({QStringLiteral("run")});
        coreProcess_->setProcessChannelMode(QProcess::MergedChannels);
        connect(coreProcess_, &QProcess::readyReadStandardOutput, this, &MainWindow::readCoreOutput);
        connect(coreProcess_, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, &MainWindow::coreFinished);
        setBusy(true, operation);
        coreProcess_->start();
        if (!coreProcess_->waitForStarted(3000)) {
            coreProcess_->deleteLater();
            coreProcess_ = nullptr;
            setBusy(false, QString());
            showError(QStringLiteral("启动 core 失败"));
            return;
        }
        coreProcess_->write(QJsonDocument(req).toJson(QJsonDocument::Compact));
        coreProcess_->closeWriteChannel();
    } catch (const std::exception &ex) {
        showError(QString::fromUtf8(ex.what()));
    }
}

void MainWindow::readCoreOutput()
{
    if (!coreProcess_) {
        return;
    }
    processBuffer_.append(coreProcess_->readAllStandardOutput());
    int newline = -1;
    while ((newline = processBuffer_.indexOf('\n')) >= 0) {
        const auto line = processBuffer_.left(newline + 1);
        processBuffer_.remove(0, newline + 1);
        for (const auto &event : parseJsonLines(line)) {
            handleEvent(event);
        }
    }
}

void MainWindow::coreFinished(int, QProcess::ExitStatus)
{
    if (!processBuffer_.trimmed().isEmpty()) {
        for (const auto &event : parseJsonLines(processBuffer_ + '\n')) {
            handleEvent(event);
        }
    }
    processBuffer_.clear();
    if (coreProcess_) {
        coreProcess_->deleteLater();
        coreProcess_ = nullptr;
    }
    setBusy(false, QString());
}

void MainWindow::handleEvent(const QJsonObject &event)
{
    const QString type = event.value(QStringLiteral("type")).toString();
    if (type == QStringLiteral("log")) {
        appendLog(event.value(QStringLiteral("line")).toString());
    } else if (type == QStringLiteral("done")) {
        handleDone(event);
    } else if (type == QStringLiteral("error")) {
        setStatus(QStringLiteral("fail"), QStringLiteral("✘ 操作失败 —— 详情见日志"));
        appendLog(event.value(QStringLiteral("message")).toString());
    }
}

void MainWindow::handleDone(const QJsonObject &event)
{
    const QString message = event.value(QStringLiteral("message")).toString();
    if (message == QStringLiteral("检测防火墙")) {
        const auto result = event.value(QStringLiteral("result")).toObject();
        fwKind_ = result.value(QStringLiteral("kind")).toString();
        fwActive_ = result.value(QStringLiteral("active")).toBool();
        updateFirewallStatus();
    }
    if (message == QStringLiteral("安装管理器") || message == QStringLiteral("升级管理器")) {
        installed_ = true;
        installBtn_->setText(QStringLiteral("✔ 已安装"));
        setStatus(QStringLiteral("ok"), QStringLiteral("✔ %1完成! 浏览器打开 http://%2:8000/").arg(message, hostEntry_->text().trimmed()));
    } else if (message == QStringLiteral("卸载管理器")) {
        installed_ = false;
        installBtn_->setText(QStringLiteral("③ 安装管理器"));
        setStatus(QStringLiteral("ok"), QStringLiteral("✔ 已卸载(游戏存档与数据库已保留)"));
    } else if (message == QStringLiteral("系统准备")) {
        aptBtn_->setText(QStringLiteral("✔ 系统已准备"));
        setStatus(QStringLiteral("ok"), QStringLiteral("✔ 系统已更新、环境就绪"));
    } else if (message == QStringLiteral("放行端口")) {
        setStatus(QStringLiteral("ok"), QStringLiteral("✔ 系统防火墙已放行。云安全组仍需放行同一端口。"));
    } else {
        setStatus(QStringLiteral("ok"), QStringLiteral("✔ %1完成").arg(message));
    }
}

void MainWindow::setBusy(bool busy, const QString &operation)
{
    QList<QPushButton *> buttons{saveBtn_, deleteBtn_, testBtn_, aptBtn_, statusBtn_, installBtn_, updateBtn_, uninstallBtn_, fwDetectBtn_, fwAllowBtn_, fwDisableBtn_};
    for (auto *button : buttons) {
        if (button) {
            button->setEnabled(!busy);
        }
    }
    cancelBtn_->setEnabled(busy);
    if (busy) {
        setStatus(QStringLiteral("running"), QStringLiteral("⏳ 正在执行:%1").arg(operation));
    }
}

void MainWindow::cancelOperation()
{
    if (coreProcess_) {
        appendLog(QStringLiteral("正在取消当前操作 ..."));
        coreProcess_->terminate();
    }
}

void MainWindow::openLogDir()
{
    if (logDir_.isEmpty()) {
        showError(QStringLiteral("日志目录尚未初始化"));
        return;
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(logDir_));
}

void MainWindow::openConfigDir()
{
    QString dir;
    if (!configPath_.isEmpty()) {
        dir = QFileInfo(configPath_).absolutePath();
    }
    if (dir.isEmpty() && !logDir_.isEmpty()) {
        dir = QFileInfo(logDir_).absolutePath();
    }
    if (dir.isEmpty()) {
        loadPaths();
        if (!configPath_.isEmpty()) {
            dir = QFileInfo(configPath_).absolutePath();
        }
    }
    if (dir.isEmpty()) {
        showError(QStringLiteral("持久化目录尚未初始化"));
        return;
    }
    QDir().mkpath(dir);
    QDesktopServices::openUrl(QUrl::fromLocalFile(dir));
}

int MainWindow::firewallPort() const
{
    bool ok = false;
    const int port = fwPortEntry_->text().trimmed().toInt(&ok);
    if (!ok || port <= 0 || port > 65535) {
        throw std::runtime_error("端口必须是 1-65535 的整数");
    }
    return port;
}

QPair<bool, bool> MainWindow::protoFlags() const
{
    switch (fwProtoSelect_->currentIndex()) {
    case 1:
        return {true, false};
    case 2:
        return {false, true};
    default:
        return {true, true};
    }
}

void MainWindow::updateFirewallStatus()
{
    if (fwKind_.isEmpty() || fwKind_ == QStringLiteral("none")) {
        fwStatusLabel_->setText(QStringLiteral("✔ 未检测到系统防火墙。请重点确认云安全组已放行端口。"));
        fwStatusLabel_->setStyleSheet(QStringLiteral("color: #1b7f45;"));
    } else if (fwActive_) {
        fwStatusLabel_->setText(QStringLiteral("● 系统防火墙:%1(已启用)。请放行端口或关闭防火墙。").arg(fwKind_));
        fwStatusLabel_->setStyleSheet(QStringLiteral("color: #b45309;"));
    } else {
        fwStatusLabel_->setText(QStringLiteral("✔ 系统防火墙:%1(未启用)。请重点确认云安全组。").arg(fwKind_));
        fwStatusLabel_->setStyleSheet(QStringLiteral("color: #1b7f45;"));
    }
}

void MainWindow::appendLog(const QString &line)
{
    logView_->appendPlainText(line);
    logView_->moveCursor(QTextCursor::End);
}

void MainWindow::setStatus(const QString &kind, const QString &text)
{
    statusLabel_->setText(text);
    QString color = QStringLiteral("#6b7280");
    if (kind == QStringLiteral("running")) {
        color = QStringLiteral("#2563eb");
    } else if (kind == QStringLiteral("ok")) {
        color = QStringLiteral("#15803d");
    } else if (kind == QStringLiteral("fail")) {
        color = QStringLiteral("#b91c1c");
    }
    statusLabel_->setStyleSheet(QStringLiteral("color: %1; font-weight: 700;").arg(color));
}

void MainWindow::showError(const QString &message) const
{
    QMessageBox::critical(const_cast<MainWindow *>(this), QStringLiteral("出错了"), message);
}

void MainWindow::applyStyle()
{
    qApp->setStyleSheet(QStringLiteral(R"(
QWidget {
    font-family: "Microsoft YaHei UI", "Noto Sans CJK SC", "Segoe UI", sans-serif;
    font-size: 14px;
    color: #1f2933;
    background: #f6f7f9;
}
QLabel#Title {
    font-size: 22px;
    font-weight: 800;
    color: #172033;
}
QLabel#Subtitle {
    color: #64748b;
    padding-top: 6px;
}
QTabWidget::pane {
    border: 1px solid #d7dce3;
    border-radius: 8px;
    background: #ffffff;
}
QTabBar::tab {
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    color: #475569;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #0f172a;
    font-weight: 700;
}
QGroupBox {
    border: 1px solid #d9dee7;
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    background: #ffffff;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit, QComboBox, QPlainTextEdit {
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 8px 10px;
    background: #ffffff;
    selection-background-color: #2563eb;
}
QPushButton {
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 8px 14px;
    background: #ffffff;
    color: #1e293b;
    font-weight: 650;
}
QPushButton:hover {
    background: #f1f5f9;
}
QPushButton:disabled {
    color: #94a3b8;
    background: #edf1f5;
}
QPushButton[primary="true"] {
    background: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
}
QPushButton[danger="true"] {
    background: #dc2626;
    border-color: #b91c1c;
    color: #ffffff;
}
QPlainTextEdit#LogView {
    background: #0f172a;
    color: #dbeafe;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 13px;
}
QLabel#Notice {
    color: #9a3412;
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 8px;
    padding: 10px 12px;
    font-weight: 700;
}
QLabel#StatusText {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px 12px;
}
QLabel#HelpTitle {
    font-size: 20px;
    font-weight: 800;
    color: #172033;
}
)"));
}
