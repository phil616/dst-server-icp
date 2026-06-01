#!/usr/bin/env bash
# 伪 SteamCMD —— 仅用于验证安装/更新管线与代理环境注入。
echo "[fake-steamcmd] args: $*"
echo "http_proxy=${http_proxy}"
echo "https_proxy=${https_proxy}"
echo "Success! App '343050' fully installed."
exit 0
