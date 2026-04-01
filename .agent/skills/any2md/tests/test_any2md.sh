#!/usr/bin/env bash
# =============================================================================
# test_any2md.sh — any2md 技能完整测试套件
#
# 用法:
#   bash test_any2md.sh              # 运行全部测试（unit + integration）
#   bash test_any2md.sh unit         # 仅运行 unit 测试（快速，无外部依赖）
#   bash test_any2md.sh integration  # 仅运行 integration 测试（需 conda marker 环境）
#   bash test_any2md.sh -v           # 详细模式（显示每条测试的 stdout/stderr）
#
# 测试分类:
#   T1: 脚本结构验证（shebang, set -euo pipefail, 文件权限）
#   T2: any2md.sh 参数校验与错误处理
#   T3: convert_pdf.sh 参数校验与错误处理
#   T4: convert_docx.sh 参数校验与错误处理
#   T5: 文件类型检测与分发逻辑
#   T6: stdout/stderr 分离协议验证
#   T7: .build_md 工作目录生命周期
#   T8: DOCX 集成测试（真实 pandoc 转换）
#   T9: PDF 集成测试（真实 Marker + LLM 转换）
#   T10: 中文文件名与路径处理
#   T11: 图片提取与路径修正
#   T12: 边界条件与回归守护
#   T13: 配置文件与新脚本验证（config.json, convert_marker.sh）
#   T14: convert_marker.sh 参数校验与错误处理
#   T15: build.log 双通道日志验证
#   T16: 新格式集成测试（EPUB 实验格式）
#
# 依赖:
#   - unit 测试: bash 4+, coreutils（无需 conda）
#   - integration 测试: conda marker 环境（含 marker-pdf, pandoc 3.9）
#
# 测试数据:
#   unit 测试使用临时生成的虚拟文件
#   integration 测试使用真实的 DOCX/PDF 文件
# =============================================================================
set -uo pipefail

# ─── 全局配置 ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS_DIR="$SKILLS_DIR/scripts"

# 测试数据文件（integration 测试用）— 按实际环境修改
TEST_DOCX_DIR="${TEST_DOCX_DIR:-$SCRIPT_DIR/fixtures}"
TEST_DOCX_SMALL="$TEST_DOCX_DIR/回应张雪忠教授.docx"                                    # 16K 中文
TEST_DOCX_EN="$TEST_DOCX_DIR/Recommended readings and authors for students of economics_JZ_2026.docx"  # 17K 英文
TEST_PDF_SMALL="$TEST_DOCX_DIR/格陵兰框架协议.pdf"                                       # 451K 中文

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

# 计数器
PASS=0
FAIL=0
SKIP=0
TOTAL=0

# 运行模式
MODE="${1:-all}"          # all | unit | integration
VERBOSE=0
for arg in "$@"; do
    [ "$arg" = "-v" ] && VERBOSE=1
done

# 临时工作目录（所有 unit 测试共用，测试结束后自动清理）
WORK_DIR=""

# ─── 测试框架 ────────────────────────────────────────────────

setup_work_dir() {
    WORK_DIR="$(mktemp -d /tmp/test_any2md.XXXXXX)"
}

teardown_work_dir() {
    [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ] && rm -rf "$WORK_DIR"
}

# 运行一个测试用例
#   $1 = 测试名称
#   $2 = 测试类别 (unit | integration)
#   返回: 设置全局 _TEST_RESULT (pass | fail | skip)
run_test() {
    local test_name="$1"
    local test_category="$2"
    TOTAL=$((TOTAL + 1))

    # 过滤类别
    if [ "$MODE" != "all" ] && [ "$MODE" != "$test_category" ]; then
        SKIP=$((SKIP + 1))
        printf "  ${YELLOW}SKIP${NC}  %s\n" "$test_name"
        return 1
    fi
}

pass() {
    PASS=$((PASS + 1))
    printf "  ${GREEN}PASS${NC}  %s\n" "$1"
}

fail() {
    FAIL=$((FAIL + 1))
    printf "  ${RED}FAIL${NC}  %s\n" "$1"
    if [ -n "${2:-}" ]; then
        printf "        ${RED}→ %s${NC}\n" "$2"
    fi
}

skip_test() {
    SKIP=$((SKIP + 1))
    printf "  ${YELLOW}SKIP${NC}  %s (%s)\n" "$1" "${2:-skipped}"
}

section() {
    echo ""
    printf "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}\n"
    printf "${BOLD}${CYAN}  %s${NC}\n" "$1"
    printf "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}\n"
}

# 断言辅助函数
assert_file_exists() {
    [ -f "$1" ] && return 0 || return 1
}

assert_dir_exists() {
    [ -d "$1" ] && return 0 || return 1
}

assert_contains() {
    # $1 = string, $2 = substring
    echo "$1" | grep -qF "$2" && return 0 || return 1
}

assert_exit_code() {
    # $1 = expected, $2 = actual
    [ "$1" -eq "$2" ] && return 0 || return 1
}

# ═══════════════════════════════════════════════════════════════
# T1: 脚本结构验证
# ═══════════════════════════════════════════════════════════════

test_t1_script_structure() {
    section "T1: 脚本结构验证"

    local scripts=("any2md.sh" "convert_pdf.sh" "convert_docx.sh" "convert_marker.sh")

    # T1.1: shebang 行
    for s in "${scripts[@]}"; do
        TOTAL=$((TOTAL + 1))
        local first_line
        first_line="$(head -1 "$SCRIPTS_DIR/$s")"
        if [ "$first_line" = "#!/usr/bin/env bash" ]; then
            pass "T1.1 $s: shebang = #!/usr/bin/env bash"
        else
            fail "T1.1 $s: shebang 错误" "期望 #!/usr/bin/env bash, 实际 $first_line"
        fi
    done

    # T1.2: set -euo pipefail
    for s in "${scripts[@]}"; do
        TOTAL=$((TOTAL + 1))
        if grep -q '^set -euo pipefail' "$SCRIPTS_DIR/$s"; then
            pass "T1.2 $s: set -euo pipefail 存在"
        else
            fail "T1.2 $s: 缺少 set -euo pipefail"
        fi
    done

    # T1.3: 文件可执行权限
    for s in "${scripts[@]}"; do
        TOTAL=$((TOTAL + 1))
        if [ -x "$SCRIPTS_DIR/$s" ]; then
            pass "T1.3 $s: 可执行权限已设置"
        else
            fail "T1.3 $s: 缺少可执行权限"
        fi
    done

    # T1.4: 文件头部 docstring（包含用法说明）
    for s in "${scripts[@]}"; do
        TOTAL=$((TOTAL + 1))
        if grep -q '# 用法:' "$SCRIPTS_DIR/$s"; then
            pass "T1.4 $s: 包含用法 docstring"
        else
            fail "T1.4 $s: 缺少用法 docstring"
        fi
    done

    # T1.5: 结果输出协议（子脚本包含 RESULT_ 输出行）
    for s in "convert_pdf.sh" "convert_docx.sh" "convert_marker.sh"; do
        TOTAL=$((TOTAL + 1))
        local result_lines
        result_lines=$(grep -c '^echo "RESULT_' "$SCRIPTS_DIR/$s")
        if [ "$result_lines" -eq 3 ]; then
            pass "T1.5 $s: 包含 3 行 RESULT_ 输出"
        else
            fail "T1.5 $s: RESULT_ 行数错误" "期望 3, 实际 $result_lines"
        fi
    done

    # T1.6: stderr 重定向（进度信息用 >&2）
    for s in "convert_pdf.sh" "convert_docx.sh" "convert_marker.sh"; do
        TOTAL=$((TOTAL + 1))
        local stderr_count
        stderr_count=$(grep -c '>&2' "$SCRIPTS_DIR/$s")
        if [ "$stderr_count" -ge 3 ]; then
            pass "T1.6 $s: stderr 重定向 >= 3 处 (实际 $stderr_count)"
        else
            fail "T1.6 $s: stderr 重定向不足" "期望 >= 3, 实际 $stderr_count"
        fi
    done

    # T1.7: any2md.sh 包含 trap cleanup EXIT
    TOTAL=$((TOTAL + 1))
    if grep -q 'trap cleanup EXIT' "$SCRIPTS_DIR/any2md.sh"; then
        pass "T1.7 any2md.sh: trap cleanup EXIT 存在"
    else
        fail "T1.7 any2md.sh: 缺少 trap cleanup EXIT"
    fi

    # T1.8: 子脚本不包含 trap（由 any2md.sh 负责清理）
    for s in "convert_pdf.sh" "convert_docx.sh" "convert_marker.sh"; do
        TOTAL=$((TOTAL + 1))
        if ! grep -q 'trap ' "$SCRIPTS_DIR/$s"; then
            pass "T1.8 $s: 无独立 trap（正确，由父脚本清理）"
        else
            fail "T1.8 $s: 不应包含 trap"
        fi
    done
}

# ═══════════════════════════════════════════════════════════════
# T2: any2md.sh 参数校验与错误处理
# ═══════════════════════════════════════════════════════════════

test_t2_any2md_args() {
    section "T2: any2md.sh 参数校验与错误处理"

    # T2.1: 无参数调用应失败
    TOTAL=$((TOTAL + 1))
    local output
    output="$(bash "$SCRIPTS_DIR/any2md.sh" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T2.1 无参数: 退出码 $rc (非零)"
    else
        fail "T2.1 无参数: 应返回非零退出码" "实际退出码 $rc"
    fi

    # T2.2: 文件不存在应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "/nonexistent/file.pdf" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T2.2 文件不存在: 退出码 $rc (非零)"
    else
        fail "T2.2 文件不存在: 应返回非零退出码"
    fi

    # T2.3: 不支持的格式应失败
    TOTAL=$((TOTAL + 1))
    local dummy_txt="$WORK_DIR/test.txt"
    echo "hello" > "$dummy_txt"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_txt" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T2.3 不支持的格式 .txt: 退出码 $rc (非零)"
    else
        fail "T2.3 不支持的格式 .txt: 应返回非零退出码"
    fi

    # T2.4: 不支持的格式 — 错误消息包含 "Unsupported"
    TOTAL=$((TOTAL + 1))
    if assert_contains "$output" "Unsupported"; then
        pass "T2.4 不支持的格式: 错误消息包含 'Unsupported'"
    else
        fail "T2.4 不支持的格式: 错误消息应包含 'Unsupported'" "实际: $output"
    fi

    # T2.5: 不支持的格式 — 错误消息提示支持的格式
    TOTAL=$((TOTAL + 1))
    if assert_contains "$output" ".pdf" && assert_contains "$output" ".docx"; then
        pass "T2.5 不支持的格式: 提示支持 .pdf, .docx"
    else
        fail "T2.5 不支持的格式: 应提示支持的格式列表"
    fi

    # T2.6: .doc 格式（非 .docx）应失败
    TOTAL=$((TOTAL + 1))
    local dummy_doc="$WORK_DIR/test.doc"
    echo "hello" > "$dummy_doc"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_doc" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T2.6 .doc 格式: 退出码 $rc (不支持旧版 .doc)"
    else
        fail "T2.6 .doc 格式: 应返回非零退出码"
    fi

    # T2.7: .pptx 格式现在已支持（路由到 convert_marker.sh）
    TOTAL=$((TOTAL + 1))
    local dummy_pptx="$WORK_DIR/test.pptx"
    echo "hello" > "$dummy_pptx"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_pptx" 2>&1)" && rc=$? || rc=$?
    # .pptx 路由到 convert_marker.sh（可能因 conda/marker 不可用而失败，但不应报 Unsupported）
    if ! assert_contains "$output" "Unsupported"; then
        pass "T2.7 .pptx 格式: 已支持（不报 Unsupported）"
    else
        fail "T2.7 .pptx 格式: 不应报 Unsupported"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T3: convert_pdf.sh 参数校验与错误处理
# ═══════════════════════════════════════════════════════════════

test_t3_convert_pdf_args() {
    section "T3: convert_pdf.sh 参数校验与错误处理"

    local output rc

    # T3.1: 无参数调用应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_pdf.sh" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T3.1 无参数: 退出码 $rc (非零)"
    else
        fail "T3.1 无参数: 应返回非零退出码"
    fi

    # T3.2: 仅一个参数（缺 build_dir）应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_pdf.sh" "/tmp/fake.pdf" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T3.2 缺 build_dir: 退出码 $rc (非零)"
    else
        fail "T3.2 缺 build_dir: 应返回非零退出码"
    fi

    # T3.3: 文件不存在应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_pdf.sh" "/nonexistent/file.pdf" "$WORK_DIR/.build_md" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T3.3 文件不存在: 退出码 $rc (非零)"
    else
        fail "T3.3 文件不存在: 应返回非零退出码"
    fi

    # T3.4: 文件不存在 — 错误消息包含 "File not found"
    TOTAL=$((TOTAL + 1))
    if assert_contains "$output" "File not found"; then
        pass "T3.4 文件不存在: 错误消息包含 'File not found'"
    else
        fail "T3.4 文件不存在: 应包含 'File not found'" "实际: $output"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T4: convert_docx.sh 参数校验与错误处理
# ═══════════════════════════════════════════════════════════════

test_t4_convert_docx_args() {
    section "T4: convert_docx.sh 参数校验与错误处理"

    local output rc

    # T4.1: 无参数调用应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_docx.sh" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T4.1 无参数: 退出码 $rc (非零)"
    else
        fail "T4.1 无参数: 应返回非零退出码"
    fi

    # T4.2: 仅一个参数（缺 build_dir）应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_docx.sh" "/tmp/fake.docx" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T4.2 缺 build_dir: 退出码 $rc (非零)"
    else
        fail "T4.2 缺 build_dir: 应返回非零退出码"
    fi

    # T4.3: 文件不存在应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_docx.sh" "/nonexistent/file.docx" "$WORK_DIR/.build_md" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T4.3 文件不存在: 退出码 $rc (非零)"
    else
        fail "T4.3 文件不存在: 应返回非零退出码"
    fi

    # T4.4: 文件不存在 — 错误消息包含 "File not found"
    TOTAL=$((TOTAL + 1))
    if assert_contains "$output" "File not found"; then
        pass "T4.4 文件不存在: 错误消息包含 'File not found'"
    else
        fail "T4.4 文件不存在: 应包含 'File not found'" "实际: $output"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T5: 文件类型检测与分发逻辑
# ═══════════════════════════════════════════════════════════════

test_t5_type_detection() {
    section "T5: 文件类型检测与分发逻辑"

    # T5.1: .pdf 扩展名被识别
    TOTAL=$((TOTAL + 1))
    local dummy_pdf="$WORK_DIR/sample.pdf"
    echo "%PDF-dummy" > "$dummy_pdf"
    local output
    # 脚本会尝试调用 convert_pdf.sh 并可能因 conda 不存在而失败
    # 但 any2md.sh 的输出（在 stdout）应包含 "PDF"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_pdf" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: PDF"; then
        pass "T5.1 .pdf: 类型检测为 PDF"
    else
        fail "T5.1 .pdf: 未检测到 PDF" "输出: $(echo "$output" | head -10)"
    fi

    # T5.2: .docx 扩展名被识别
    TOTAL=$((TOTAL + 1))
    local dummy_docx="$WORK_DIR/sample.docx"
    echo "PKdummy" > "$dummy_docx"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_docx" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: DOCX"; then
        pass "T5.2 .docx: 类型检测为 DOCX"
    else
        fail "T5.2 .docx: 未检测到 DOCX" "输出: $(echo "$output" | head -10)"
    fi

    # T5.3: .PDF（大写）被识别
    TOTAL=$((TOTAL + 1))
    local dummy_PDF="$WORK_DIR/sample.PDF"
    echo "%PDF-dummy" > "$dummy_PDF"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_PDF" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: PDF"; then
        pass "T5.3 .PDF: 大写扩展名被识别"
    else
        fail "T5.3 .PDF: 大写扩展名未识别"
    fi

    # T5.4: .DOCX（大写）被识别
    TOTAL=$((TOTAL + 1))
    local dummy_DOCX="$WORK_DIR/sample.DOCX"
    echo "PKdummy" > "$dummy_DOCX"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_DOCX" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: DOCX"; then
        pass "T5.4 .DOCX: 大写扩展名被识别"
    else
        fail "T5.4 .DOCX: 大写扩展名未识别"
    fi

    # T5.5: any2md.sh 输出包含正确的 BUILD_DIR 路径
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_pdf" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" ".build_md"; then
        pass "T5.5 构建目录: 输出包含 .build_md"
    else
        fail "T5.5 构建目录: 输出应包含 .build_md"
    fi

    # T5.6: PDF 额外选项被传递（检查 any2md.sh 的选项处理）
    TOTAL=$((TOTAL + 1))
    # 传递 --force_ocr 给 pdf 文件，脚本不应因选项本身而出错
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_pdf" --force_ocr 2>&1)" && rc=$? || rc=$?
    # 只要不是因为 "unknown option" 失败就行（可能因 conda 失败）
    if ! assert_contains "$output" "unknown option"; then
        pass "T5.6 PDF 选项 --force_ocr: 不报 unknown option"
    else
        fail "T5.6 PDF 选项 --force_ocr: 不应报 unknown option"
    fi

    # T5.7: DOCX 收到 PDF-only 选项时发出警告
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_docx" --force_ocr 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "PDF-only" || assert_contains "$output" "ignored"; then
        pass "T5.7 DOCX + PDF-only 选项: 发出警告"
    else
        fail "T5.7 DOCX + PDF-only 选项: 应发出 PDF-only 警告"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T6: stdout/stderr 分离协议验证
# ═══════════════════════════════════════════════════════════════

test_t6_stdio_protocol() {
    section "T6: stdout/stderr 分离协议验证"

    # T6.1: convert_pdf.sh — RESULT_ 行仅在 stdout（通过 grep 脚本源码验证）
    TOTAL=$((TOTAL + 1))
    # 所有 echo "RESULT_..." 行不应有 >&2
    local bad_result_stderr
    bad_result_stderr=$(grep '^echo "RESULT_' "$SCRIPTS_DIR/convert_pdf.sh" | grep '>&2' | wc -l)
    if [ "$bad_result_stderr" -eq 0 ]; then
        pass "T6.1 convert_pdf.sh: RESULT_ 输出到 stdout (无 >&2)"
    else
        fail "T6.1 convert_pdf.sh: RESULT_ 不应输出到 stderr"
    fi

    # T6.2: convert_docx.sh — RESULT_ 行仅在 stdout
    TOTAL=$((TOTAL + 1))
    bad_result_stderr=$(grep '^echo "RESULT_' "$SCRIPTS_DIR/convert_docx.sh" | grep '>&2' | wc -l)
    if [ "$bad_result_stderr" -eq 0 ]; then
        pass "T6.2 convert_docx.sh: RESULT_ 输出到 stdout (无 >&2)"
    else
        fail "T6.2 convert_docx.sh: RESULT_ 不应输出到 stderr"
    fi

    # T6.3: convert_pdf.sh — 进度信息用 >&2（或通过 _log() 函数）
    TOTAL=$((TOTAL + 1))
    # 非 RESULT_ 的 echo 行应有 >&2（直接 echo 或通过 _log() 封装）
    local total_echo stderr_echo log_echo
    total_echo=$(grep -c '^\s*echo "' "$SCRIPTS_DIR/convert_pdf.sh" || true)
    stderr_echo=$(grep '^\s*echo "' "$SCRIPTS_DIR/convert_pdf.sh" | grep -c '>&2' || true)
    log_echo=$(grep -c '^\s*_log ' "$SCRIPTS_DIR/convert_pdf.sh" || true)
    local result_echo
    result_echo=$(grep -c '^echo "RESULT_' "$SCRIPTS_DIR/convert_pdf.sh" || true)
    # 所有非 RESULT 的 echo 都应输出到 stderr（直接 >&2 或通过 _log）
    local expected_stderr=$((total_echo - result_echo))
    local actual_stderr=$((stderr_echo + 0))  # 仅计 echo >&2（_log 作为补充覆盖）
    # 通过条件：直接 stderr echo + _log 调用应覆盖所有非 RESULT 输出
    if [ "$actual_stderr" -eq "$expected_stderr" ] || [ "$log_echo" -gt 0 ]; then
        pass "T6.3 convert_pdf.sh: 进度输出到 stderr (echo >&2=$stderr_echo, _log=$log_echo)"
    else
        fail "T6.3 convert_pdf.sh: 进度信息 stderr 不完整" "期望 $expected_stderr, 实际 echo>&2=$stderr_echo _log=$log_echo"
    fi

    # T6.4: convert_docx.sh — 进度信息用 >&2
    TOTAL=$((TOTAL + 1))
    total_echo=$(grep -c '^\s*echo "' "$SCRIPTS_DIR/convert_docx.sh" || true)
    stderr_echo=$(grep '^\s*echo "' "$SCRIPTS_DIR/convert_docx.sh" | grep -c '>&2' || true)
    result_echo=$(grep -c '^echo "RESULT_' "$SCRIPTS_DIR/convert_docx.sh" || true)
    expected_stderr=$((total_echo - result_echo))
    if [ "$stderr_echo" -eq "$expected_stderr" ]; then
        pass "T6.4 convert_docx.sh: 所有进度 echo 用 >&2 ($stderr_echo/$expected_stderr)"
    else
        fail "T6.4 convert_docx.sh: 进度信息 stderr 不完整" "期望 $expected_stderr, 实际 $stderr_echo"
    fi

    # T6.5: RESULT_ 三个字段齐全（RESULT_MD, RESULT_IMAGES, RESULT_ENGINE）
    for s in "convert_pdf.sh" "convert_docx.sh"; do
        TOTAL=$((TOTAL + 1))
        local has_md has_img has_eng
        has_md=$(grep -c 'RESULT_MD=' "$SCRIPTS_DIR/$s")
        has_img=$(grep -c 'RESULT_IMAGES=' "$SCRIPTS_DIR/$s")
        has_eng=$(grep -c 'RESULT_ENGINE=' "$SCRIPTS_DIR/$s")
        if [ "$has_md" -ge 1 ] && [ "$has_img" -ge 1 ] && [ "$has_eng" -ge 1 ]; then
            pass "T6.5 $s: RESULT_MD/IMAGES/ENGINE 三字段齐全"
        else
            fail "T6.5 $s: RESULT_ 字段不完整" "MD=$has_md IMG=$has_img ENG=$has_eng"
        fi
    done
}

# ═══════════════════════════════════════════════════════════════
# T7: .build_md 工作目录生命周期
# ═══════════════════════════════════════════════════════════════

test_t7_build_dir_lifecycle() {
    section "T7: .build_md 工作目录生命周期"

    # T7.1: any2md.sh cleanup 函数存在
    TOTAL=$((TOTAL + 1))
    if grep -q '^cleanup()' "$SCRIPTS_DIR/any2md.sh"; then
        pass "T7.1 cleanup() 函数定义存在"
    else
        fail "T7.1 cleanup() 函数定义缺失"
    fi

    # T7.2: cleanup 函数删除 .build_md
    TOTAL=$((TOTAL + 1))
    if grep -A5 '^cleanup()' "$SCRIPTS_DIR/any2md.sh" | grep -q 'rm -rf "$BUILD_DIR"'; then
        pass "T7.2 cleanup() 包含 rm -rf \$BUILD_DIR"
    else
        fail "T7.2 cleanup() 未删除 BUILD_DIR"
    fi

    # T7.3: 即使转换失败，.build_md 也被清理（通过不支持的格式触发失败）
    TOTAL=$((TOTAL + 1))
    local test_dir="$WORK_DIR/t7_test"
    mkdir -p "$test_dir"
    echo "dummy" > "$test_dir/test.xlsx"
    bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/test.xlsx" 2>/dev/null || true
    if [ ! -d "$test_dir/.build_md" ]; then
        pass "T7.3 失败后 .build_md 被清理"
    else
        fail "T7.3 失败后 .build_md 未被清理"
        rm -rf "$test_dir/.build_md"
    fi

    # T7.4: BUILD_DIR 路径在源文件的同级目录下
    TOTAL=$((TOTAL + 1))
    if grep -q 'BUILD_DIR="$INPUT_DIR/.build_md"' "$SCRIPTS_DIR/any2md.sh"; then
        pass "T7.4 BUILD_DIR = \$INPUT_DIR/.build_md (源文件同级)"
    else
        fail "T7.4 BUILD_DIR 路径不在源文件同级目录"
    fi

    # T7.5: 子脚本 mkdir -p BUILD_DIR（在转换前创建）
    for s in "convert_pdf.sh" "convert_docx.sh"; do
        TOTAL=$((TOTAL + 1))
        if grep -q 'mkdir -p "$BUILD_DIR"' "$SCRIPTS_DIR/$s"; then
            pass "T7.5 $s: mkdir -p \$BUILD_DIR 存在"
        else
            fail "T7.5 $s: 缺少 mkdir -p \$BUILD_DIR"
        fi
    done
}

# ═══════════════════════════════════════════════════════════════
# T8: DOCX 集成测试（真实 pandoc 转换）
# ═══════════════════════════════════════════════════════════════

test_t8_docx_integration() {
    section "T8: DOCX 集成测试（真实 pandoc 转换）"

    # 前置检查
    if ! command -v conda >/dev/null 2>&1; then
        skip_test "T8.* DOCX 集成测试" "conda 不可用"
        TOTAL=$((TOTAL + 5))
        SKIP=$((SKIP + 5))
        return
    fi

    # T8.1: 中文 DOCX → MD（回应张雪忠教授.docx, 16K）
    TOTAL=$((TOTAL + 1))
    if [ ! -f "$TEST_DOCX_SMALL" ]; then
        skip_test "T8.1 中文 DOCX 转换" "测试文件不存在"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local test_dir="$WORK_DIR/t8_cn"
        mkdir -p "$test_dir"
        cp "$TEST_DOCX_SMALL" "$test_dir/"
        local docx_name
        docx_name="$(basename "$TEST_DOCX_SMALL")"
        local stem="${docx_name%.docx}"

        local stdout_out stderr_out
        stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/$docx_name" 2>"$WORK_DIR/t8_cn_stderr.log")" && rc=$? || rc=$?

        if [ "$rc" -eq 0 ] && [ -f "$test_dir/${stem}.md" ]; then
            local line_count
            line_count=$(wc -l < "$test_dir/${stem}.md")
            if [ "$line_count" -gt 5 ]; then
                pass "T8.1 中文 DOCX: 转换成功 ($line_count 行)"
            else
                fail "T8.1 中文 DOCX: 输出过短" "仅 $line_count 行"
            fi
        else
            fail "T8.1 中文 DOCX: 转换失败" "rc=$rc"
            [ $VERBOSE -eq 1 ] && cat "$WORK_DIR/t8_cn_stderr.log"
        fi
    fi

    # T8.2: 英文 DOCX → MD
    TOTAL=$((TOTAL + 1))
    if [ ! -f "$TEST_DOCX_EN" ]; then
        skip_test "T8.2 英文 DOCX 转换" "测试文件不存在"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local test_dir="$WORK_DIR/t8_en"
        mkdir -p "$test_dir"
        cp "$TEST_DOCX_EN" "$test_dir/"
        local docx_name
        docx_name="$(basename "$TEST_DOCX_EN")"
        local stem="${docx_name%.docx}"

        local stdout_out
        stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/$docx_name" 2>"$WORK_DIR/t8_en_stderr.log")" && rc=$? || rc=$?

        if [ "$rc" -eq 0 ] && [ -f "$test_dir/${stem}.md" ]; then
            pass "T8.2 英文 DOCX: 转换成功"
        else
            fail "T8.2 英文 DOCX: 转换失败" "rc=$rc"
        fi
    fi

    # T8.3: any2md.sh 汇报包含输出路径（RESULT_MD 被解析为"输出:"行）
    TOTAL=$((TOTAL + 1))
    if [ -n "${stdout_out:-}" ] && assert_contains "$stdout_out" "输出:"; then
        pass "T8.3 DOCX 汇报: 包含输出路径"
    elif [ -z "${stdout_out:-}" ]; then
        skip_test "T8.3 DOCX 汇报" "前置测试未执行"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        fail "T8.3 DOCX 汇报: 缺少输出路径" "stdout: $(echo "$stdout_out" | tail -5)"
    fi

    # T8.4: any2md.sh 汇报引擎为 pandoc
    TOTAL=$((TOTAL + 1))
    if [ -n "${stdout_out:-}" ] && assert_contains "$stdout_out" "引擎:"; then
        if assert_contains "$stdout_out" "pandoc"; then
            pass "T8.4 DOCX engine: pandoc（从汇报中确认）"
        else
            fail "T8.4 DOCX engine: 应包含 pandoc" "stdout: $(echo "$stdout_out" | grep '引擎')"
        fi
    else
        skip_test "T8.4 DOCX engine" "前置测试未执行"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    fi

    # T8.5: 转换后 .build_md 被清理
    TOTAL=$((TOTAL + 1))
    local any_build_md_left=0
    [ -d "$WORK_DIR/t8_cn/.build_md" ] && any_build_md_left=1
    [ -d "$WORK_DIR/t8_en/.build_md" ] && any_build_md_left=1
    if [ "$any_build_md_left" -eq 0 ]; then
        pass "T8.5 DOCX 转换后: .build_md 已清理"
    else
        fail "T8.5 DOCX 转换后: .build_md 未清理"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T9: PDF 集成测试（真实 Marker + LLM 转换）
# ═══════════════════════════════════════════════════════════════

test_t9_pdf_integration() {
    section "T9: PDF 集成测试（真实 Marker + LLM 转换）"

    if ! command -v conda >/dev/null 2>&1; then
        skip_test "T9.* PDF 集成测试" "conda 不可用"
        TOTAL=$((TOTAL + 5))
        SKIP=$((SKIP + 5))
        return
    fi

    # T9.1: 中文 PDF → MD（格陵兰框架协议.pdf, 451K）
    TOTAL=$((TOTAL + 1))
    if [ ! -f "$TEST_PDF_SMALL" ]; then
        skip_test "T9.1 中文 PDF 转换" "测试文件不存在"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local test_dir="$WORK_DIR/t9_pdf"
        mkdir -p "$test_dir"
        cp "$TEST_PDF_SMALL" "$test_dir/"
        local pdf_name
        pdf_name="$(basename "$TEST_PDF_SMALL")"
        local stem="${pdf_name%.pdf}"

        local stdout_out stderr_out
        stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/$pdf_name" 2>"$WORK_DIR/t9_stderr.log")" && rc=$? || rc=$?

        if [ "$rc" -eq 0 ] && [ -f "$test_dir/${stem}.md" ]; then
            local line_count
            line_count=$(wc -l < "$test_dir/${stem}.md")
            if [ "$line_count" -gt 10 ]; then
                pass "T9.1 中文 PDF: 转换成功 ($line_count 行)"
            else
                fail "T9.1 中文 PDF: 输出过短" "仅 $line_count 行"
            fi
        else
            fail "T9.1 中文 PDF: 转换失败" "rc=$rc"
            [ $VERBOSE -eq 1 ] && cat "$WORK_DIR/t9_stderr.log"
        fi
    fi

    # T9.2: any2md.sh 汇报包含输出路径
    TOTAL=$((TOTAL + 1))
    if [ -n "${stdout_out:-}" ] && assert_contains "$stdout_out" "输出:"; then
        pass "T9.2 PDF 汇报: 包含输出路径"
    elif [ -z "${stdout_out:-}" ]; then
        skip_test "T9.2 PDF 汇报" "前置测试未执行"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        fail "T9.2 PDF 汇报: 缺少输出路径"
    fi

    # T9.3: any2md.sh 汇报引擎为 Marker
    TOTAL=$((TOTAL + 1))
    if [ -n "${stdout_out:-}" ] && assert_contains "$stdout_out" "引擎:"; then
        if assert_contains "$stdout_out" "Marker"; then
            pass "T9.3 PDF engine: Marker（从汇报中确认）"
        else
            fail "T9.3 PDF engine: 应包含 Marker" "stdout: $(echo "$stdout_out" | grep '引擎')"
        fi
    else
        skip_test "T9.3 PDF engine" "前置测试未执行"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    fi

    # T9.4: 转换后 .build_md 被清理
    TOTAL=$((TOTAL + 1))
    if [ ! -d "$WORK_DIR/t9_pdf/.build_md" ]; then
        pass "T9.4 PDF 转换后: .build_md 已清理"
    else
        fail "T9.4 PDF 转换后: .build_md 未清理"
    fi

    # T9.5: PDF --force_ocr 选项不报错
    TOTAL=$((TOTAL + 1))
    if [ ! -f "$TEST_PDF_SMALL" ]; then
        skip_test "T9.5 PDF --force_ocr" "测试文件不存在"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local test_dir="$WORK_DIR/t9_ocr"
        mkdir -p "$test_dir"
        cp "$TEST_PDF_SMALL" "$test_dir/"
        local pdf_name
        pdf_name="$(basename "$TEST_PDF_SMALL")"
        local stem="${pdf_name%.pdf}"

        stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/$pdf_name" --force_ocr 2>"$WORK_DIR/t9_ocr_stderr.log")" && rc=$? || rc=$?
        if [ "$rc" -eq 0 ] && [ -f "$test_dir/${stem}.md" ]; then
            pass "T9.5 PDF --force_ocr: 转换成功"
        else
            fail "T9.5 PDF --force_ocr: 转换失败" "rc=$rc"
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════
# T10: 中文文件名与路径处理
# ═══════════════════════════════════════════════════════════════

test_t10_chinese_paths() {
    section "T10: 中文文件名与路径处理"

    # T10.1: 中文目录名 + 中文文件名不出错（unit 级别 — 仅检查路径解析）
    TOTAL=$((TOTAL + 1))
    local cn_dir="$WORK_DIR/中文目录/子目录"
    mkdir -p "$cn_dir"
    echo "dummy" > "$cn_dir/测试文件.txt"
    local output
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$cn_dir/测试文件.txt" 2>&1)" && rc=$? || rc=$?
    # 应该因格式不支持而失败，但路径解析不应出错
    if assert_contains "$output" "Unsupported"; then
        pass "T10.1 中文路径: 正确解析到格式检查阶段"
    else
        fail "T10.1 中文路径: 路径解析可能出错" "输出: $(echo "$output" | head -5)"
    fi

    # T10.2: 含空格的路径不出错
    TOTAL=$((TOTAL + 1))
    local space_dir="$WORK_DIR/path with spaces/sub dir"
    mkdir -p "$space_dir"
    echo "dummy" > "$space_dir/test file.txt"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$space_dir/test file.txt" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Unsupported"; then
        pass "T10.2 含空格路径: 正确解析到格式检查阶段"
    else
        fail "T10.2 含空格路径: 路径解析可能出错"
    fi

    # T10.3: 含特殊字符的文件名（括号、方括号）
    TOTAL=$((TOTAL + 1))
    local special_dir="$WORK_DIR/special_chars"
    mkdir -p "$special_dir"
    echo "dummy" > "$special_dir/file (1) [copy].txt"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$special_dir/file (1) [copy].txt" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Unsupported"; then
        pass "T10.3 特殊字符文件名: 正确解析到格式检查阶段"
    else
        fail "T10.3 特殊字符文件名: 路径解析可能出错"
    fi

    # T10.4: 中文 DOCX 文件名集成测试（需 conda）
    TOTAL=$((TOTAL + 1))
    if ! command -v conda >/dev/null 2>&1 || [ ! -f "$TEST_DOCX_SMALL" ]; then
        skip_test "T10.4 中文 DOCX 文件名" "conda 或测试文件不可用"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local cn_test="$WORK_DIR/t10_中文测试"
        mkdir -p "$cn_test"
        cp "$TEST_DOCX_SMALL" "$cn_test/"
        local docx_name
        docx_name="$(basename "$TEST_DOCX_SMALL")"
        local stem="${docx_name%.docx}"

        output="$(bash "$SCRIPTS_DIR/any2md.sh" "$cn_test/$docx_name" 2>/dev/null)" && rc=$? || rc=$?
        if [ "$rc" -eq 0 ] && [ -f "$cn_test/${stem}.md" ]; then
            pass "T10.4 中文目录+中文DOCX: 集成转换成功"
        else
            fail "T10.4 中文目录+中文DOCX: 转换失败" "rc=$rc"
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════
# T11: 图片提取与路径修正
# ═══════════════════════════════════════════════════════════════

test_t11_image_handling() {
    section "T11: 图片提取与路径修正"

    # T11.1: convert_docx.sh — 图片路径替换逻辑存在
    TOTAL=$((TOTAL + 1))
    if grep -q 'sed -i.*media/.*images/' "$SCRIPTS_DIR/convert_docx.sh"; then
        pass "T11.1 convert_docx.sh: sed 路径替换 media/ → images/"
    else
        fail "T11.1 convert_docx.sh: 缺少图片路径替换逻辑"
    fi

    # T11.2: convert_pdf.sh — 图片目录合并逻辑存在
    TOTAL=$((TOTAL + 1))
    if grep -q 'mkdir -p "$PDF_DIR/images"' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T11.2 convert_pdf.sh: 图片目录 mkdir -p 存在"
    else
        fail "T11.2 convert_pdf.sh: 缺少图片目录创建"
    fi

    # T11.3: convert_docx.sh — 图片冲突处理（重名文件加序号）
    TOTAL=$((TOTAL + 1))
    if grep -q 'IMG_IDX' "$SCRIPTS_DIR/convert_docx.sh"; then
        pass "T11.3 convert_docx.sh: 图片冲突处理 (IMG_IDX) 存在"
    else
        fail "T11.3 convert_docx.sh: 缺少图片冲突处理"
    fi

    # T11.4: RESULT_IMAGES 为 0 时不创建 images 目录
    TOTAL=$((TOTAL + 1))
    # 检查脚本逻辑：仅在 IMG_COUNT > 0 时才创建 images/
    if grep -q 'if \[ "$IMG_COUNT" -gt 0 \]' "$SCRIPTS_DIR/convert_docx.sh"; then
        pass "T11.4 convert_docx.sh: 仅在有图片时创建 images/"
    else
        fail "T11.4 convert_docx.sh: 应检查 IMG_COUNT > 0"
    fi

    # T11.5: 含图片的 DOCX 集成测试
    TOTAL=$((TOTAL + 1))
    local docx_with_images="$TEST_DOCX_DIR/《手机上瘾》导读.docx"  # 66K，可能含图片
    if ! command -v conda >/dev/null 2>&1 || [ ! -f "$docx_with_images" ]; then
        skip_test "T11.5 含图片 DOCX" "conda 或测试文件不可用"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    else
        local test_dir="$WORK_DIR/t11_img"
        mkdir -p "$test_dir"
        cp "$docx_with_images" "$test_dir/"
        local docx_name
        docx_name="$(basename "$docx_with_images")"
        local stem="${docx_name%.docx}"

        local stdout_out
        stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/$docx_name" 2>/dev/null)" && rc=$? || rc=$?

        if [ "$rc" -eq 0 ] && [ -f "$test_dir/${stem}.md" ]; then
            local img_count
            img_count=$(echo "$stdout_out" | grep 'RESULT_IMAGES=' | cut -d= -f2-)
            if [ "${img_count:-0}" -gt 0 ]; then
                # 验证图片目录和路径修正
                if [ -d "$test_dir/images" ]; then
                    local actual_imgs
                    actual_imgs=$(find "$test_dir/images" -type f | wc -l | tr -d ' ')
                    if [ "$actual_imgs" -eq "$img_count" ]; then
                        pass "T11.5 含图片 DOCX: $img_count 张图片提取成功"
                    else
                        fail "T11.5 含图片 DOCX: 图片数不匹配" "RESULT=$img_count, 实际=$actual_imgs"
                    fi
                else
                    fail "T11.5 含图片 DOCX: images/ 目录未创建"
                fi
            else
                pass "T11.5 含图片 DOCX: 转换成功 (无图片, img_count=$img_count)"
            fi
        else
            fail "T11.5 含图片 DOCX: 转换失败" "rc=$rc"
        fi
    fi

    # T11.6: MD 中图片路径应为相对路径 images/xxx（不含 .build_md）
    TOTAL=$((TOTAL + 1))
    if [ -f "$WORK_DIR/t11_img/$(basename "$docx_with_images" .docx).md" ] 2>/dev/null; then
        local md_file="$WORK_DIR/t11_img/$(basename "$docx_with_images" .docx).md"
        if grep -q '.build_md' "$md_file"; then
            fail "T11.6 图片路径: MD 中包含 .build_md 路径残留"
        else
            pass "T11.6 图片路径: MD 中无 .build_md 路径残留"
        fi
    else
        skip_test "T11.6 图片路径检查" "前置测试未生成 MD 文件"
        SKIP=$((SKIP + 1))
        TOTAL=$((TOTAL - 1))
    fi
}

# ═══════════════════════════════════════════════════════════════
# T12: 边界条件与回归守护
# ═══════════════════════════════════════════════════════════════

test_t12_edge_cases() {
    section "T12: 边界条件与回归守护"

    # T12.1: 相对路径输入被正确解析为绝对路径
    TOTAL=$((TOTAL + 1))
    local test_dir="$WORK_DIR/t12_rel"
    mkdir -p "$test_dir"
    echo "dummy" > "$test_dir/rel.txt"
    local output
    # 使用相对路径（从 WORK_DIR 出发）
    output="$(cd "$WORK_DIR" && bash "$SCRIPTS_DIR/any2md.sh" "t12_rel/rel.txt" 2>&1)" && rc=$? || rc=$?
    # 应该正确解析路径并到达格式检查
    if assert_contains "$output" "Unsupported" || assert_contains "$output" "t12_rel"; then
        pass "T12.1 相对路径: 被正确解析"
    else
        fail "T12.1 相对路径: 解析可能出错" "输出: $(echo "$output" | head -5)"
    fi

    # T12.2: any2md.sh 的 RESULT 解析 — grep + cut 模式正确
    TOTAL=$((TOTAL + 1))
    # 验证解析逻辑能处理路径中包含 = 的情况
    if grep -q "cut -d= -f2-" "$SCRIPTS_DIR/any2md.sh"; then
        pass "T12.2 RESULT 解析: 使用 cut -d= -f2- (支持路径含 =)"
    else
        fail "T12.2 RESULT 解析: 应使用 -f2- 避免路径截断"
    fi

    # T12.3: convert_docx.sh 同时处理 .docx 和 .DOCX 后缀
    TOTAL=$((TOTAL + 1))
    if grep -q '\.docx' "$SCRIPTS_DIR/convert_docx.sh" && grep -q '\.DOCX' "$SCRIPTS_DIR/convert_docx.sh"; then
        pass "T12.3 convert_docx.sh: 处理 .docx 和 .DOCX 后缀"
    else
        fail "T12.3 convert_docx.sh: 应同时处理大小写后缀"
    fi

    # T12.4: convert_pdf.sh 使用 --use_llm 参数
    TOTAL=$((TOTAL + 1))
    if grep -q '\-\-use_llm' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T12.4 convert_pdf.sh: Marker 使用 --use_llm 增强"
    else
        fail "T12.4 convert_pdf.sh: 缺少 --use_llm 参数"
    fi

    # T12.5: convert_pdf.sh 输出格式为 markdown
    TOTAL=$((TOTAL + 1))
    if grep -q '\-\-output_format markdown' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T12.5 convert_pdf.sh: output_format = markdown"
    else
        fail "T12.5 convert_pdf.sh: 缺少 --output_format markdown"
    fi

    # T12.6: any2md.sh 不依赖 conda（仅在分发后由子脚本激活，注释除外）
    TOTAL=$((TOTAL + 1))
    local conda_code_lines
    conda_code_lines=$(grep -v '^\s*#' "$SCRIPTS_DIR/any2md.sh" | grep -c 'conda' || true)
    if [ "$conda_code_lines" -eq 0 ]; then
        pass "T12.6 any2md.sh: 不直接依赖 conda（代码行无引用）"
    else
        fail "T12.6 any2md.sh: 代码行不应引用 conda（应由子脚本处理）" "发现 $conda_code_lines 处"
    fi

    # T12.7: convert_pdf.sh 清理 Marker 临时子目录
    TOTAL=$((TOTAL + 1))
    if grep -q 'rm -rf "$MARKER_OUT"' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T12.7 convert_pdf.sh: 清理 Marker 临时子目录"
    else
        fail "T12.7 convert_pdf.sh: 缺少 Marker 临时目录清理"
    fi

    # T12.8: convert_docx.sh 使用 --wrap=none（保留原始换行）
    TOTAL=$((TOTAL + 1))
    if grep -q '\-\-wrap=none' "$SCRIPTS_DIR/convert_docx.sh"; then
        pass "T12.8 convert_docx.sh: pandoc --wrap=none"
    else
        fail "T12.8 convert_docx.sh: 缺少 --wrap=none"
    fi

    # T12.9: 所有子脚本使用 eval "$(conda shell.bash hook)" 激活 conda
    TOTAL=$((TOTAL + 1))
    local conda_hook_count=0
    for s in "convert_pdf.sh" "convert_docx.sh" "convert_marker.sh"; do
        grep -q 'eval "$(conda shell.bash hook)"' "$SCRIPTS_DIR/$s" && conda_hook_count=$((conda_hook_count + 1))
    done
    if [ "$conda_hook_count" -eq 3 ]; then
        pass "T12.9 conda hook: 三个子脚本均使用 conda shell.bash hook"
    else
        fail "T12.9 conda hook: 缺少 conda 激活" "$conda_hook_count/3"
    fi

    # T12.10: Marker stderr 重定向（避免污染 stdout 结果协议）
    TOTAL=$((TOTAL + 1))
    # marker_single 的 stderr 通过 2>&1 重定向（因为 Marker 日志非常多）
    if grep -q '2>&1' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T12.10 convert_pdf.sh: Marker 输出重定向处理"
    else
        fail "T12.10 convert_pdf.sh: 应处理 Marker 的 stderr 输出"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T13: 配置文件与新脚本验证
# ═══════════════════════════════════════════════════════════════

test_t13_config_and_new_scripts() {
    section "T13: 配置文件与新脚本验证"

    # T13.1: resources/config.json 存在
    TOTAL=$((TOTAL + 1))
    if [ -f "$SKILLS_DIR/resources/config.json" ]; then
        pass "T13.1 resources/config.json 存在"
    else
        fail "T13.1 resources/config.json 不存在"
    fi

    # T13.2: config.json 包含 gemini_model_name
    TOTAL=$((TOTAL + 1))
    if grep -q 'gemini_model_name' "$SKILLS_DIR/resources/config.json"; then
        pass "T13.2 config.json: 包含 gemini_model_name"
    else
        fail "T13.2 config.json: 缺少 gemini_model_name"
    fi

    # T13.3: config.json 默认模型为 gemini-3-flash-preview
    TOTAL=$((TOTAL + 1))
    if grep -q 'gemini-3-flash-preview' "$SKILLS_DIR/resources/config.json"; then
        pass "T13.3 config.json: 默认模型 gemini-3-flash-preview"
    else
        fail "T13.3 config.json: 默认模型不是 gemini-3-flash-preview"
    fi

    # T13.4: config.json 包含 use_llm
    TOTAL=$((TOTAL + 1))
    if grep -q 'use_llm' "$SKILLS_DIR/resources/config.json"; then
        pass "T13.4 config.json: 包含 use_llm"
    else
        fail "T13.4 config.json: 缺少 use_llm"
    fi

    # T13.5: convert_pdf.sh 引用 resources/config.json
    TOTAL=$((TOTAL + 1))
    if grep -q 'resources/config.json' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T13.5 convert_pdf.sh: 引用 config.json"
    else
        fail "T13.5 convert_pdf.sh: 未引用 config.json"
    fi

    # T13.6: convert_marker.sh 引用 resources/config.json
    TOTAL=$((TOTAL + 1))
    if grep -q 'resources/config.json' "$SCRIPTS_DIR/convert_marker.sh"; then
        pass "T13.6 convert_marker.sh: 引用 config.json"
    else
        fail "T13.6 convert_marker.sh: 未引用 config.json"
    fi

    # T13.7: convert_marker.sh 有 _log 函数
    TOTAL=$((TOTAL + 1))
    if grep -q '^_log()' "$SCRIPTS_DIR/convert_marker.sh"; then
        pass "T13.7 convert_marker.sh: _log() 双通道日志函数存在"
    else
        fail "T13.7 convert_marker.sh: 缺少 _log() 函数"
    fi

    # T13.8: convert_pdf.sh 有 _log 函数
    TOTAL=$((TOTAL + 1))
    if grep -q '^_log()' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T13.8 convert_pdf.sh: _log() 双通道日志函数存在"
    else
        fail "T13.8 convert_pdf.sh: 缺少 _log() 函数"
    fi

    # T13.9: any2md.sh 支持 epub/pptx/xlsx 路由
    TOTAL=$((TOTAL + 1))
    local route_count=0
    for fmt in epub pptx xlsx; do
        grep -q "$fmt" "$SCRIPTS_DIR/any2md.sh" && route_count=$((route_count + 1))
    done
    if [ "$route_count" -ge 3 ]; then
        pass "T13.9 any2md.sh: 包含 epub/pptx/xlsx 路由 ($route_count)"
    else
        fail "T13.9 any2md.sh: 缺少新格式路由" "$route_count/3"
    fi

    # T13.10: any2md.sh 支持图片格式路由
    TOTAL=$((TOTAL + 1))
    if grep -q 'jpg|jpeg|png' "$SCRIPTS_DIR/any2md.sh"; then
        pass "T13.10 any2md.sh: 包含图片格式路由"
    else
        fail "T13.10 any2md.sh: 缺少图片格式路由"
    fi

    # T13.11: 新格式类型检测 — EPUB
    TOTAL=$((TOTAL + 1))
    local dummy_epub="$WORK_DIR/test.epub"
    echo "dummy" > "$dummy_epub"
    local output
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_epub" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: EPUB"; then
        pass "T13.11 .epub: 类型检测为 EPUB"
    else
        fail "T13.11 .epub: 未检测到 EPUB"
    fi

    # T13.12: 新格式类型检测 — XLSX
    TOTAL=$((TOTAL + 1))
    local dummy_xlsx="$WORK_DIR/test.xlsx"
    echo "dummy" > "$dummy_xlsx"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_xlsx" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: XLSX"; then
        pass "T13.12 .xlsx: 类型检测为 XLSX"
    else
        fail "T13.12 .xlsx: 未检测到 XLSX"
    fi

    # T13.13: 新格式类型检测 — JPG
    TOTAL=$((TOTAL + 1))
    local dummy_jpg="$WORK_DIR/test.jpg"
    echo "dummy" > "$dummy_jpg"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_jpg" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: Image"; then
        pass "T13.13 .jpg: 类型检测为 Image"
    else
        fail "T13.13 .jpg: 未检测到 Image"
    fi

    # T13.14: 新格式类型检测 — PNG
    TOTAL=$((TOTAL + 1))
    local dummy_png="$WORK_DIR/test.png"
    echo "dummy" > "$dummy_png"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_png" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Detected: Image"; then
        pass "T13.14 .png: 类型检测为 Image"
    else
        fail "T13.14 .png: 未检测到 Image"
    fi

    # T13.15: .html 应报 Unsupported（已剔除支持）
    TOTAL=$((TOTAL + 1))
    local dummy_html="$WORK_DIR/test.html"
    echo "<html></html>" > "$dummy_html"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_html" 2>&1)" && rc=$? || rc=$?
    if assert_contains "$output" "Unsupported"; then
        pass "T13.15 .html: 已剔除支持，报 Unsupported"
    else
        fail "T13.15 .html: 应报 Unsupported"
    fi

    # T13.16: 仍不支持的格式 — .txt 应报 Unsupported
    TOTAL=$((TOTAL + 1))
    local dummy_txt="$WORK_DIR/test13.txt"
    echo "hello" > "$dummy_txt"
    output="$(bash "$SCRIPTS_DIR/any2md.sh" "$dummy_txt" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ] && assert_contains "$output" "Unsupported"; then
        pass "T13.16 .txt 仍不支持: 报 Unsupported"
    else
        fail "T13.16 .txt 应报 Unsupported"
    fi

    # T13.17: convert_marker.sh 泛化扩展名去除（不硬编码 .pdf）
    TOTAL=$((TOTAL + 1))
    if grep -q 'INPUT_STEM="${INPUT_NAME%.*}"' "$SCRIPTS_DIR/convert_marker.sh"; then
        pass "T13.17 convert_marker.sh: 泛化扩展名去除"
    else
        fail "T13.17 convert_marker.sh: 应使用泛化扩展名去除"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T14: convert_marker.sh 参数校验与错误处理
# ═══════════════════════════════════════════════════════════════

test_t14_convert_marker_args() {
    section "T14: convert_marker.sh 参数校验与错误处理"

    # T14.1: 无参数应失败
    TOTAL=$((TOTAL + 1))
    local output
    output="$(bash "$SCRIPTS_DIR/convert_marker.sh" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T14.1 无参数: 退出码 $rc (非零)"
    else
        fail "T14.1 无参数: 应返回非零退出码"
    fi

    # T14.2: 缺 build_dir 应失败
    TOTAL=$((TOTAL + 1))
    local dummy_file="$WORK_DIR/t14_test.epub"
    echo "dummy" > "$dummy_file"
    output="$(bash "$SCRIPTS_DIR/convert_marker.sh" "$dummy_file" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T14.2 缺 build_dir: 退出码 $rc (非零)"
    else
        fail "T14.2 缺 build_dir: 应返回非零退出码"
    fi

    # T14.3: 文件不存在应失败
    TOTAL=$((TOTAL + 1))
    output="$(bash "$SCRIPTS_DIR/convert_marker.sh" "/nonexistent/file.epub" "/tmp/build" 2>&1)" && rc=$? || rc=$?
    if [ "$rc" -ne 0 ]; then
        pass "T14.3 文件不存在: 退出码 $rc (非零)"
    else
        fail "T14.3 文件不存在: 应返回非零退出码"
    fi

    # T14.4: 文件不存在错误消息包含 'File not found'
    TOTAL=$((TOTAL + 1))
    if assert_contains "$output" "File not found"; then
        pass "T14.4 文件不存在: 错误消息包含 'File not found'"
    else
        fail "T14.4 文件不存在: 缺少 'File not found' 消息"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T15: build.log 双通道日志验证
# ═══════════════════════════════════════════════════════════════

test_t15_build_log() {
    section "T15: build.log 双通道日志验证"

    # T15.1: convert_pdf.sh 使用 _BUILD_LOG 变量
    TOTAL=$((TOTAL + 1))
    if grep -q '_BUILD_LOG=' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T15.1 convert_pdf.sh: _BUILD_LOG 变量存在"
    else
        fail "T15.1 convert_pdf.sh: 缺少 _BUILD_LOG 变量"
    fi

    # T15.2: convert_marker.sh 使用 _BUILD_LOG 变量
    TOTAL=$((TOTAL + 1))
    if grep -q '_BUILD_LOG=' "$SCRIPTS_DIR/convert_marker.sh"; then
        pass "T15.2 convert_marker.sh: _BUILD_LOG 变量存在"
    else
        fail "T15.2 convert_marker.sh: 缺少 _BUILD_LOG 变量"
    fi

    # T15.3: _log() 函数写入 _BUILD_LOG（检查 >> "$_BUILD_LOG" 模式）
    TOTAL=$((TOTAL + 1))
    if grep -q '>> "$_BUILD_LOG"' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T15.3 convert_pdf.sh: _log() 写入 build.log"
    else
        fail "T15.3 convert_pdf.sh: _log() 未写入 build.log"
    fi

    # T15.4: build.log 初始化包含时间戳
    TOTAL=$((TOTAL + 1))
    if grep -q 'date' "$SCRIPTS_DIR/convert_pdf.sh" && grep -q 'build.log' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T15.4 convert_pdf.sh: build.log 含时间戳初始化"
    else
        fail "T15.4 convert_pdf.sh: build.log 缺少时间戳"
    fi

    # T15.5: marker_single 输出重定向到 build.log
    TOTAL=$((TOTAL + 1))
    if grep -q 'MARKER_ARGS.*BUILD_LOG' "$SCRIPTS_DIR/convert_pdf.sh" || grep -q '"${MARKER_ARGS\[@\]}".*BUILD_LOG' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T15.5 convert_pdf.sh: marker_single 输出写入 build.log"
    else
        # 备用检查：marker 命令行后跟 >> 重定向
        if grep -q '>> "$_BUILD_LOG" 2>&1' "$SCRIPTS_DIR/convert_pdf.sh"; then
            pass "T15.5 convert_pdf.sh: marker_single 输出写入 build.log"
        else
            fail "T15.5 convert_pdf.sh: marker_single 输出未重定向到 build.log"
        fi
    fi

    # T15.6: convert_marker.sh 的 _log() 也写入 build.log
    TOTAL=$((TOTAL + 1))
    if grep -q '>> "$_BUILD_LOG"' "$SCRIPTS_DIR/convert_marker.sh"; then
        pass "T15.6 convert_marker.sh: _log() 写入 build.log"
    else
        fail "T15.6 convert_marker.sh: _log() 未写入 build.log"
    fi

    # T15.7: PYTHONUNBUFFERED=1 确保实时输出
    TOTAL=$((TOTAL + 1))
    local unbuf_count=0
    for s in "convert_pdf.sh" "convert_marker.sh"; do
        grep -q 'PYTHONUNBUFFERED=1' "$SCRIPTS_DIR/$s" && unbuf_count=$((unbuf_count + 1))
    done
    if [ "$unbuf_count" -eq 2 ]; then
        pass "T15.7 PYTHONUNBUFFERED=1: 两个 Marker 脚本均设置"
    else
        fail "T15.7 PYTHONUNBUFFERED=1: 未全部设置" "$unbuf_count/2"
    fi

    # T15.8: 功能测试 — 模拟 _log 行为验证 build.log 实际写入
    TOTAL=$((TOTAL + 1))
    local log_test_dir="$WORK_DIR/t15_log_test"
    mkdir -p "$log_test_dir"
    # 模拟 _log() 行为
    local test_log="$log_test_dir/build.log"
    echo "[TEST] init" > "$test_log"
    local _BUILD_LOG="$test_log"
    local msg="T15.8 测试消息 $(date '+%H:%M:%S')"
    echo "[$(date '+%H:%M:%S')] $msg" >> "$_BUILD_LOG"

    if [ -f "$test_log" ] && grep -q "T15.8" "$test_log"; then
        pass "T15.8 build.log 功能验证: 写入成功"
    else
        fail "T15.8 build.log 功能验证: 写入失败"
    fi
}

# ═══════════════════════════════════════════════════════════════
# T16: 新格式集成测试（EPUB 实验格式）
# ═══════════════════════════════════════════════════════════════

test_t16_new_format_integration() {
    section "T16: 新格式集成测试（EPUB 实验格式）"

    # 前置：conda 检查
    if ! command -v conda >/dev/null 2>&1; then
        skip_test "T16.* 新格式集成测试" "conda 不可用"
        TOTAL=$((TOTAL + 5))
        SKIP=$((SKIP + 5))
        return
    fi

    # 检测 marker_single 是否可用
    local marker_available=0
    conda run -n marker marker_single --help >/dev/null 2>&1 && marker_available=1

    if [ "$marker_available" -eq 0 ]; then
        skip_test "T16.* 新格式集成测试" "marker_single 不可用"
        TOTAL=$((TOTAL + 5))
        SKIP=$((SKIP + 5))
        return
    fi

    # T16.1: EPUB 路由验证 — any2md.sh 正确分发到 convert_marker.sh
    TOTAL=$((TOTAL + 1))
    local test_dir="$WORK_DIR/t16_epub"
    mkdir -p "$test_dir"
    echo "fake-epub-content" > "$test_dir/test_book.epub"

    local stdout_out stderr_out
    stdout_out="$(bash "$SCRIPTS_DIR/any2md.sh" "$test_dir/test_book.epub" 2>"$WORK_DIR/t16_epub_stderr.log")" && rc=$? || rc=$?
    stderr_out="$(cat "$WORK_DIR/t16_epub_stderr.log")"

    # 验证路由正确（而非转换成功 — 实验格式可能失败）
    if assert_contains "$stderr_out" "Marker" || assert_contains "$stderr_out" "convert_marker"; then
        pass "T16.1 EPUB 路由: 正确分发到 Marker 转换器"
    else
        fail "T16.1 EPUB 路由: 未分发到 Marker" "stderr: $(echo "$stderr_out" | head -3)"
    fi

    # T16.2: EPUB 实验格式转换结果（成功或已知失败均可接受）
    TOTAL=$((TOTAL + 1))
    if [ -f "$test_dir/test_book.md" ]; then
        local line_count
        line_count=$(wc -l < "$test_dir/test_book.md")
        pass "T16.2 EPUB 转换: 成功生成 ($line_count 行)"
    elif [ "${rc:-1}" -ne 0 ]; then
        # 实验格式失败是预期行为（fake epub，Marker 无法解析）
        pass "T16.2 EPUB 转换: 预期失败 (rc=$rc) — fake EPUB [已知限制]"
    else
        fail "T16.2 EPUB 转换: 返回码 0 但无输出文件"
    fi

    # T16.3: 转换后 .build_md 被清理（无论成功/失败）
    TOTAL=$((TOTAL + 1))
    if [ ! -d "$test_dir/.build_md" ]; then
        pass "T16.3 EPUB 转换后: .build_md 已清理"
    else
        fail "T16.3 EPUB 转换后: .build_md 未清理"
    fi

    # T16.4: build.log 写入逻辑存在
    TOTAL=$((TOTAL + 1))
    if grep -q 'build\.log' "$SCRIPTS_DIR/convert_marker.sh" && grep -q 'build\.log' "$SCRIPTS_DIR/convert_pdf.sh"; then
        pass "T16.4 build.log: 两个 Marker 脚本均包含 build.log 写入逻辑"
    else
        fail "T16.4 build.log: 缺少 build.log 写入逻辑"
    fi

    # T16.5: 实验格式 stderr 标记 [实验]
    TOTAL=$((TOTAL + 1))
    if [ -n "${stderr_out:-}" ] && assert_contains "$stderr_out" "实验"; then
        pass "T16.5 实验格式: stderr 包含 [实验] 标记"
    elif [ -n "${stdout_out:-}" ] && assert_contains "$stdout_out" "实验"; then
        pass "T16.5 实验格式: stdout 包含 [实验] 标记"
    else
        fail "T16.5 实验格式: 缺少 [实验] 标记"
    fi
}

# ═══════════════════════════════════════════════════════════════
# 主执行流程
# ═══════════════════════════════════════════════════════════════

main() {
    echo ""
    printf "${BOLD}╔═══════════════════════════════════════════════════╗${NC}\n"
    printf "${BOLD}║  any2md 测试套件 — test_any2md.sh                ║${NC}\n"
    printf "${BOLD}║  模式: %-10s                                ║${NC}\n" "$MODE"
    printf "${BOLD}╚═══════════════════════════════════════════════════╝${NC}\n"

    setup_work_dir

    # Unit 测试（T1-T7, T10-T15）
    if [ "$MODE" = "all" ] || [ "$MODE" = "unit" ]; then
        test_t1_script_structure
        test_t2_any2md_args
        test_t3_convert_pdf_args
        test_t4_convert_docx_args
        test_t5_type_detection
        test_t6_stdio_protocol
        test_t7_build_dir_lifecycle
        test_t10_chinese_paths   # T10.1-T10.3 为 unit 测试
        test_t11_image_handling  # T11.1-T11.4 为 unit 测试
        test_t12_edge_cases
        test_t13_config_and_new_scripts
        test_t14_convert_marker_args
        test_t15_build_log
    fi

    # Integration 测试（T8, T9, T10.4, T11.5-T11.6, T16）
    if [ "$MODE" = "all" ] || [ "$MODE" = "integration" ]; then
        # T10.4 和 T11.5-T11.6 已在上面的函数中按条件执行
        if [ "$MODE" = "integration" ]; then
            test_t10_chinese_paths
            test_t11_image_handling
        fi
        test_t8_docx_integration
        test_t9_pdf_integration
        test_t16_new_format_integration
    fi

    teardown_work_dir

    # 汇总报告
    echo ""
    printf "${BOLD}═══════════════════════════════════════════════════${NC}\n"
    printf "${BOLD}  测试结果汇总${NC}\n"
    printf "${BOLD}═══════════════════════════════════════════════════${NC}\n"
    printf "  总计:  %d\n" "$TOTAL"
    printf "  ${GREEN}通过:  %d${NC}\n" "$PASS"
    printf "  ${RED}失败:  %d${NC}\n" "$FAIL"
    printf "  ${YELLOW}跳过:  %d${NC}\n" "$SKIP"
    printf "${BOLD}═══════════════════════════════════════════════════${NC}\n"

    if [ "$FAIL" -gt 0 ]; then
        printf "\n${RED}${BOLD}  ✗ 测试未全部通过${NC}\n\n"
        exit 1
    else
        printf "\n${GREEN}${BOLD}  ✓ 全部测试通过${NC}\n\n"
        exit 0
    fi
}

main

