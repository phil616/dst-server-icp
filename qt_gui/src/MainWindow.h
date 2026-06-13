#pragma once

#include <QJsonObject>
#include <QMainWindow>
#include <QProcess>

class QCheckBox;
class QComboBox;
class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QPushButton;
class QTabWidget;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

private slots:
    void loadConfig();
    void saveProfile();
    void deleteProfile();
    void selectProfile(int index);
    void runOperation(const QString &operation);
    void readCoreOutput();
    void coreFinished(int exitCode, QProcess::ExitStatus status);
    void cancelOperation();
    void openLogDir();

private:
    QWidget *buildDeployTab();
    QWidget *buildFirewallTab();
    QWidget *buildSettingsTab();
    QWidget *buildHelpTab();
    QPushButton *actionButton(const QString &text, const QString &operation, bool primary = false, bool danger = false);

    QString locateCore() const;
    void applyStyle();
    void refreshProfiles(const QString &selected);
    void fillProfile(const QJsonObject &profile);
    QJsonObject profileFromForm() const;
    QJsonObject baseRequest() const;
    QJsonObject callCore(const QString &command, const QJsonObject &payload = {}) const;
    QList<QJsonObject> parseJsonLines(const QByteArray &data) const;
    void handleEvent(const QJsonObject &event);
    void handleDone(const QJsonObject &event);
    void setBusy(bool busy, const QString &operation);
    void setStatus(const QString &kind, const QString &text);
    void appendLog(const QString &line);
    int firewallPort() const;
    QPair<bool, bool> protoFlags() const;
    void updateFirewallStatus();
    void showError(const QString &message) const;

    QString corePath_;
    QString configPath_;
    QString logDir_;
    QProcess *coreProcess_ = nullptr;
    QByteArray processBuffer_;
    QList<QJsonObject> profiles_;
    bool installed_ = false;
    QString fwKind_;
    bool fwActive_ = false;

    QTabWidget *tabs_ = nullptr;
    QLabel *statusLabel_ = nullptr;

    QComboBox *profileSelect_ = nullptr;
    QLineEdit *nameEntry_ = nullptr;
    QLineEdit *hostEntry_ = nullptr;
    QLineEdit *portEntry_ = nullptr;
    QLineEdit *userEntry_ = nullptr;
    QLineEdit *passEntry_ = nullptr;
    QLineEdit *mirrorEntry_ = nullptr;
    QCheckBox *sudoCheck_ = nullptr;
    QCheckBox *upgradeCheck_ = nullptr;
    QPlainTextEdit *logView_ = nullptr;

    QPushButton *saveBtn_ = nullptr;
    QPushButton *deleteBtn_ = nullptr;
    QPushButton *testBtn_ = nullptr;
    QPushButton *aptBtn_ = nullptr;
    QPushButton *statusBtn_ = nullptr;
    QPushButton *installBtn_ = nullptr;
    QPushButton *updateBtn_ = nullptr;
    QPushButton *uninstallBtn_ = nullptr;
    QPushButton *cancelBtn_ = nullptr;
    QPushButton *fwDetectBtn_ = nullptr;
    QPushButton *fwAllowBtn_ = nullptr;
    QPushButton *fwDisableBtn_ = nullptr;

    QLabel *fwStatusLabel_ = nullptr;
    QLineEdit *fwPortEntry_ = nullptr;
    QComboBox *fwProtoSelect_ = nullptr;
};

