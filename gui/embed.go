package main

import _ "embed"

// installScript 是随程序内置的 install-dst.sh。
// 构建前由 build.sh 从仓库根目录同步到 scripts/ 下,保证与项目脚本一致。
//
//go:embed scripts/install-dst.sh
var installScript []byte
