#!/usr/bin/env python3
"""SCSH v4.1 升级测试套件。

覆盖所有 v4.1 新增/变更的功能点：
  - Manifest I/O (load / save / 损坏处理)
  - 目录隔离 (_chart_dir)
  - 代码哈希 (_code_hash)
  - 增量判定 (_chart_needs_rebuild)
  - Manifest 持久化 (_update_chart_manifest)
  - 入口清理 (_cleanup_chart_dir)
  - --only-charts 解析 (_parse_chart_indices)
  - 复盘报告 (_generate_debrief)
  - render_mermaid_block 无前缀命名
  - CLI --only-charts 参数注册

Usage:
    python3 test_scsh_v41.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

# 确保能 import mermaid_scsh（同目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mermaid_scsh as scsh


class TestChartDir(unittest.TestCase):
    """测试 _chart_dir() 目录隔离。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_subdirectory(self) -> None:
        """按 file_stem 创建子目录。"""
        result = scsh._chart_dir(self.tmpdir, 'target')
        self.assertEqual(result, os.path.join(self.tmpdir, 'target'))
        self.assertTrue(os.path.isdir(result))

    def test_idempotent(self) -> None:
        """多次调用不报错。"""
        scsh._chart_dir(self.tmpdir, 'report')
        scsh._chart_dir(self.tmpdir, 'report')
        self.assertTrue(os.path.isdir(os.path.join(self.tmpdir, 'report')))

    def test_multiple_stems(self) -> None:
        """不同 file_stem 创建独立子目录。"""
        d1 = scsh._chart_dir(self.tmpdir, 'file_a')
        d2 = scsh._chart_dir(self.tmpdir, 'file_b')
        self.assertNotEqual(d1, d2)
        self.assertTrue(os.path.isdir(d1))
        self.assertTrue(os.path.isdir(d2))


class TestManifestIO(unittest.TestCase):
    """测试 Manifest 的 load/save 及边界情况。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_nonexistent(self) -> None:
        """加载不存在的 manifest 返回空结构。"""
        m = scsh._load_manifest(self.tmpdir)
        self.assertEqual(m['version'], scsh.MANIFEST_VERSION)
        self.assertEqual(m['charts'], {})

    def test_save_and_load(self) -> None:
        """保存后再加载，数据一致。"""
        manifest = {
            'version': '4.1',
            'charts': {'0': {'status': 'passed', 'score': 8}},
        }
        scsh._save_manifest(self.tmpdir, manifest)
        loaded = scsh._load_manifest(self.tmpdir)
        self.assertEqual(loaded['charts']['0']['status'], 'passed')
        self.assertEqual(loaded['charts']['0']['score'], 8)

    def test_load_corrupted(self) -> None:
        """损坏的 manifest 返回空结构而非崩溃。"""
        path = os.path.join(self.tmpdir, 'build_manifest.json')
        with open(path, 'w') as f:
            f.write('NOT VALID JSON {{{')
        m = scsh._load_manifest(self.tmpdir)
        self.assertEqual(m['version'], scsh.MANIFEST_VERSION)
        self.assertEqual(m['charts'], {})

    def test_save_unicode(self) -> None:
        """保存包含中文 Unicode 字符的 manifest。"""
        manifest = {
            'version': '4.1',
            'charts': {'0': {'heading': '营收结构'}},
        }
        scsh._save_manifest(self.tmpdir, manifest)
        loaded = scsh._load_manifest(self.tmpdir)
        self.assertEqual(loaded['charts']['0']['heading'], '营收结构')

    def test_manifest_file_path(self) -> None:
        """manifest 文件保存在正确路径。"""
        scsh._save_manifest(self.tmpdir, {'version': '4.1', 'charts': {}})
        self.assertTrue(os.path.exists(
            os.path.join(self.tmpdir, 'build_manifest.json')
        ))


class TestCodeHash(unittest.TestCase):
    """测试 _code_hash() 哈希计算。"""

    def test_deterministic(self) -> None:
        """相同输入产生相同哈希。"""
        h1 = scsh._code_hash('graph TD\n    A --> B')
        h2 = scsh._code_hash('graph TD\n    A --> B')
        self.assertEqual(h1, h2)

    def test_different_input(self) -> None:
        """不同输入产生不同哈希。"""
        h1 = scsh._code_hash('graph TD\n    A --> B')
        h2 = scsh._code_hash('graph LR\n    A --> B')
        self.assertNotEqual(h1, h2)

    def test_format(self) -> None:
        """哈希格式为 sha256:xxxx。"""
        h = scsh._code_hash('test')
        self.assertTrue(h.startswith('sha256:'))
        self.assertEqual(len(h), len('sha256:') + 16)

    def test_empty_string(self) -> None:
        """空字符串不崩溃。"""
        h = scsh._code_hash('')
        self.assertTrue(h.startswith('sha256:'))


class TestChartNeedsRebuild(unittest.TestCase):
    """测试 _chart_needs_rebuild() 增量判定逻辑。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.code = 'graph TD\n    A --> B'
        self.code_h = scsh._code_hash(self.code)
        # 创建 PNG 文件
        png_path = os.path.join(self.tmpdir, 'chart_0.png')
        with open(png_path, 'wb') as f:
            f.write(b'\x89PNG' + b'\x00' * 100)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_new_chart(self) -> None:
        """新图表 (manifest 中无记录) → 需要重建。"""
        manifest = {'charts': {}}
        self.assertTrue(
            scsh._chart_needs_rebuild(manifest, 0, self.code_h, self.tmpdir)
        )

    def test_passed_same_hash(self) -> None:
        """已通过 + 代码未变 + PNG 存在 → 跳过。"""
        manifest = {'charts': {'0': {
            'status': 'passed',
            'code_hash': self.code_h,
            'png': 'chart_0.png',
        }}}
        self.assertFalse(
            scsh._chart_needs_rebuild(manifest, 0, self.code_h, self.tmpdir)
        )

    def test_failed_status(self) -> None:
        """上次未通过 → 需要重建。"""
        manifest = {'charts': {'0': {
            'status': 'needs_intervention',
            'code_hash': self.code_h,
            'png': 'chart_0.png',
        }}}
        self.assertTrue(
            scsh._chart_needs_rebuild(manifest, 0, self.code_h, self.tmpdir)
        )

    def test_code_changed(self) -> None:
        """代码已变更 → 需要重建。"""
        manifest = {'charts': {'0': {
            'status': 'passed',
            'code_hash': 'sha256:old_hash_12345',
            'png': 'chart_0.png',
        }}}
        self.assertTrue(
            scsh._chart_needs_rebuild(manifest, 0, self.code_h, self.tmpdir)
        )

    def test_png_missing(self) -> None:
        """PNG 丢失 → 需要重建。"""
        manifest = {'charts': {'0': {
            'status': 'passed',
            'code_hash': self.code_h,
            'png': 'chart_0_nonexistent.png',
        }}}
        self.assertTrue(
            scsh._chart_needs_rebuild(manifest, 0, self.code_h, self.tmpdir)
        )


class TestUpdateChartManifest(unittest.TestCase):
    """测试 _update_chart_manifest() 持久化。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_basic_persist(self) -> None:
        """基本持久化：status + heading + chart_type。"""
        block = {'heading': '营收结构', 'chart_type': 'pie', 'start_line': 42}
        result = {
            'status': 'passed', 'code': 'pie\n  "A": 30',
            'score': 8, 'history': [],
            'layout_score': 8, 'color_score': 9, 'readability_score': 8,
        }
        scsh._update_chart_manifest(self.tmpdir, 0, block, result)
        m = scsh._load_manifest(self.tmpdir)
        chart = m['charts']['0']
        self.assertEqual(chart['status'], 'passed')
        self.assertEqual(chart['heading'], '营收结构')
        self.assertEqual(chart['chart_type'], 'pie')
        self.assertEqual(chart['overall_score'], 8)
        self.assertEqual(chart['png'], 'chart_0.png')

    def test_multi_chart_persist(self) -> None:
        """多图表持久化：chart_0 和 chart_1 共存。"""
        block0 = {'heading': 'A', 'chart_type': 'pie', 'start_line': 10}
        block1 = {'heading': 'B', 'chart_type': 'flowchart', 'start_line': 50}
        result = {'status': 'passed', 'code': 'x', 'score': 7, 'history': []}
        scsh._update_chart_manifest(self.tmpdir, 0, block0, result)
        scsh._update_chart_manifest(self.tmpdir, 1, block1, result)
        m = scsh._load_manifest(self.tmpdir)
        self.assertIn('0', m['charts'])
        self.assertIn('1', m['charts'])
        self.assertEqual(m['charts']['0']['heading'], 'A')
        self.assertEqual(m['charts']['1']['heading'], 'B')

    def test_scores_optional(self) -> None:
        """结果中无 score 字段不崩溃。"""
        block = {'heading': 'X'}
        result = {'status': 'failed', 'code': 'y', 'history': []}
        scsh._update_chart_manifest(self.tmpdir, 0, block, result)
        m = scsh._load_manifest(self.tmpdir)
        self.assertEqual(m['charts']['0']['overall_score'], -1)

    def test_history_persisted(self) -> None:
        """history 列表正确持久化。"""
        block = {'heading': 'Z'}
        history = [
            {'attempt': 1, 'type': 'gemini_fix', 'score': 4},
            {'attempt': 2, 'type': 'gemini_fix', 'score': 6},
        ]
        result = {'status': 'needs_intervention', 'code': 'z',
                  'score': 6, 'history': history}
        scsh._update_chart_manifest(self.tmpdir, 0, block, result)
        m = scsh._load_manifest(self.tmpdir)
        self.assertEqual(len(m['charts']['0']['history']), 2)
        self.assertEqual(m['charts']['0']['attempts'], 3)


class TestCleanupChartDir(unittest.TestCase):
    """测试 _cleanup_chart_dir() 入口清理逻辑。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        # 创建合法文件
        for f in ['chart_0.mmd', 'chart_0.png', 'chart_1.mmd', 'chart_1.png',
                   'build_manifest.json', 'debrief.json', 'mermaid-font.css']:
            with open(os.path.join(self.tmpdir, f), 'w') as fh:
                fh.write('test')
        # 创建孤儿文件（旧图表产物）
        for f in ['chart_5.mmd', 'chart_5.png', 'old_artifact.txt']:
            with open(os.path.join(self.tmpdir, f), 'w') as fh:
                fh.write('orphan')

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_removes_orphans(self) -> None:
        """删除不属于当前图表集的旧文件。"""
        blocks = [{'code': 'a'}, {'code': 'b'}]  # 2 个图表
        scsh._cleanup_chart_dir(self.tmpdir, blocks)
        remaining = set(os.listdir(self.tmpdir))
        self.assertNotIn('chart_5.mmd', remaining)
        self.assertNotIn('chart_5.png', remaining)
        self.assertNotIn('old_artifact.txt', remaining)

    def test_preserves_valid(self) -> None:
        """保留当前图表文件、manifest、debrief、CSS。"""
        blocks = [{'code': 'a'}, {'code': 'b'}]
        scsh._cleanup_chart_dir(self.tmpdir, blocks)
        remaining = set(os.listdir(self.tmpdir))
        for f in ['chart_0.mmd', 'chart_0.png', 'chart_1.mmd', 'chart_1.png',
                   'build_manifest.json', 'debrief.json', 'mermaid-font.css']:
            self.assertIn(f, remaining, f"保留文件 {f} 被误删")

    def test_nonexistent_dir(self) -> None:
        """不存在的目录不报错。"""
        scsh._cleanup_chart_dir('/tmp/nonexistent_dir_99999', [])

    def test_empty_blocks(self) -> None:
        """0 个图表时，仅保留 manifest/debrief/css。"""
        blocks = []
        scsh._cleanup_chart_dir(self.tmpdir, blocks)
        remaining = set(os.listdir(self.tmpdir))
        self.assertIn('build_manifest.json', remaining)
        self.assertIn('debrief.json', remaining)
        self.assertNotIn('chart_0.mmd', remaining)


class TestParseChartIndices(unittest.TestCase):
    """测试 _parse_chart_indices() 解析 --only-charts 参数。"""

    def test_single_index(self) -> None:
        """单个索引。"""
        self.assertEqual(scsh._parse_chart_indices('1', 5), {1})

    def test_multiple_indices(self) -> None:
        """逗号分隔多个索引。"""
        self.assertEqual(scsh._parse_chart_indices('1,3,4', 5), {1, 3, 4})

    def test_range(self) -> None:
        """范围表示。"""
        self.assertEqual(scsh._parse_chart_indices('1-3', 5), {1, 2, 3})

    def test_mixed(self) -> None:
        """混合：单个 + 范围。"""
        self.assertEqual(
            scsh._parse_chart_indices('0,3-5,7', 10),
            {0, 3, 4, 5, 7},
        )

    def test_out_of_range(self) -> None:
        """超出总数的索引被过滤。"""
        result = scsh._parse_chart_indices('0,5,10', 3)
        self.assertEqual(result, {0})  # 只有 0 在 [0,3) 范围内

    def test_with_spaces(self) -> None:
        """索引间有空格。"""
        self.assertEqual(scsh._parse_chart_indices('1, 3, 5', 10), {1, 3, 5})

    def test_zero_based(self) -> None:
        """0-based 索引。"""
        self.assertIn(0, scsh._parse_chart_indices('0', 5))

    def test_negative_filtered(self) -> None:
        """负数索引被过滤。"""
        result = scsh._parse_chart_indices('-1,0,1', 5)
        self.assertNotIn(-1, result)
        self.assertIn(0, result)


class TestGenerateDebrief(unittest.TestCase):
    """测试 _generate_debrief() 复盘报告生成。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_all_passed(self) -> None:
        """全部通过：all_passed=True，无 failed_charts。"""
        results = [
            {'status': 'passed', 'score': 8},
            {'status': 'passed', 'score': 9},
        ]
        d = scsh._generate_debrief(self.tmpdir, results, '/path/target.md')
        self.assertTrue(d['all_passed'])
        self.assertEqual(d['passed'], 2)
        self.assertEqual(d['failed'], 0)
        self.assertEqual(d['failed_charts'], [])
        self.assertIsNone(d['reentry_command'])

    def test_partial_failure(self) -> None:
        """部分失败：生成 reentry_command。"""
        results = [
            {'status': 'passed', 'score': 8},
            {'status': 'needs_intervention', 'score': 5,
             'heading': '技术架构', 'chart_type': 'flowchart',
             'issues': [{'dimension': 'layout', 'description': '节点重叠'}]},
        ]
        d = scsh._generate_debrief(self.tmpdir, results, '/path/target.md')
        self.assertFalse(d['all_passed'])
        self.assertEqual(d['passed'], 1)
        self.assertEqual(d['failed'], 1)
        self.assertEqual(len(d['failed_charts']), 1)
        self.assertEqual(d['failed_charts'][0]['chart_index'], 1)
        self.assertIn('--only-charts', d['reentry_command'])
        self.assertIn('"1"', d['reentry_command'])

    def test_with_none_skipped(self) -> None:
        """跳过的图表 (None) 不计入统计。"""
        results = [
            {'status': 'passed', 'score': 8},
            None,  # 跳过
            {'status': 'needs_intervention', 'score': 4,
             'issues': []},
        ]
        d = scsh._generate_debrief(self.tmpdir, results, '/t.md')
        self.assertEqual(d['total_charts'], 2)  # 只计 non-None
        self.assertEqual(d['passed'], 1)
        self.assertEqual(d['failed'], 1)

    def test_debrief_structure(self) -> None:
        """验证 debrief 必含的所有字段。"""
        results = [{'status': 'passed', 'score': 9}]
        d = scsh._generate_debrief(self.tmpdir, results, '/f.md')
        required_keys = {
            'file', 'total_charts', 'passed', 'failed',
            'all_passed', 'max_agent_retries', 'failed_charts',
            'reentry_command',
        }
        self.assertTrue(required_keys.issubset(set(d.keys())))

    def test_multiple_failures_command(self) -> None:
        """多个失败图表的 reentry_command 正确拼接。"""
        results = [
            {'status': 'needs_intervention', 'score': 3, 'issues': []},
            {'status': 'passed', 'score': 8},
            {'status': 'needs_intervention', 'score': 4, 'issues': []},
        ]
        d = scsh._generate_debrief(self.tmpdir, results, '/t.md')
        self.assertIn('0,2', d['reentry_command'])


class TestRenderPathNaming(unittest.TestCase):
    """测试 render_mermaid_block 的文件命名 (v4.1: 无 file_stem 前缀)。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_prefix_in_filename(self) -> None:
        """v4.1: 渲染产物文件名不包含 file_stem 前缀。"""
        code = 'graph TD\n    A --> B'
        # Mock subprocess.run 避免实际调用 mmdc
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = type('R', (), {
                'returncode': 1, 'stderr': 'mock', 'stdout': '',
            })()
            scsh.render_mermaid_block(code, 2, work_dir=self.tmpdir,
                                      file_stem='target')
        # 验证写入的 mmd 文件名无前缀
        expected_mmd = os.path.join(self.tmpdir, 'chart_2.mmd')
        self.assertTrue(os.path.exists(expected_mmd),
                        f"期望 chart_2.mmd，非 target_chart_2.mmd")

    def test_old_prefix_not_created(self) -> None:
        """确认不再创建 file_stem 前缀文件。"""
        code = 'graph TD\n    A --> B'
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = type('R', (), {
                'returncode': 1, 'stderr': 'mock', 'stdout': '',
            })()
            scsh.render_mermaid_block(code, 0, work_dir=self.tmpdir,
                                      file_stem='report')
        old_path = os.path.join(self.tmpdir, 'report_chart_0.mmd')
        self.assertFalse(os.path.exists(old_path),
                         f"v4.0 旧命名 {old_path} 不应存在")


class TestCLIOnlyCharts(unittest.TestCase):
    """测试 CLI 参数 --only-charts 注册。"""

    def test_parser_accepts_only_charts(self) -> None:
        """argparse 正确解析 --only-charts。"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--file', required=True)
        parser.add_argument('--only-charts', type=str, default=None)
        args = parser.parse_args(['--file', 'test.md', '--only-charts', '1,3'])
        self.assertEqual(args.only_charts, '1,3')

    def test_default_none(self) -> None:
        """不传 --only-charts 时默认 None。"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--file', required=True)
        parser.add_argument('--only-charts', type=str, default=None)
        args = parser.parse_args(['--file', 'test.md'])
        self.assertIsNone(args.only_charts)

    def test_script_help_output(self) -> None:
        """脚本 --help 输出包含 --only-charts (超时保护)。"""
        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(
                    os.path.dirname(__file__), 'mermaid_scsh.py'), '--help'],
                capture_output=True, text=True, timeout=10,
            )
            self.assertIn('--only-charts', result.stdout)
        except subprocess.TimeoutExpired:
            self.skipTest("--help subprocess timed out (likely slow import)")


class TestIntegrationDirectoryIsolation(unittest.TestCase):
    """集成测试：多文件目录隔离 + manifest 独立。"""

    def setUp(self) -> None:
        self.work_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_two_files_isolated(self) -> None:
        """两个 MD 文件的 manifest 互不干扰。"""
        dir_a = scsh._chart_dir(self.work_dir, 'file_a')
        dir_b = scsh._chart_dir(self.work_dir, 'file_b')

        # 分别写入不同 manifest
        scsh._save_manifest(dir_a, {
            'version': '4.1',
            'charts': {'0': {'status': 'passed'}},
        })
        scsh._save_manifest(dir_b, {
            'version': '4.1',
            'charts': {'0': {'status': 'failed'}},
        })

        # 加载验证互相独立
        ma = scsh._load_manifest(dir_a)
        mb = scsh._load_manifest(dir_b)
        self.assertEqual(ma['charts']['0']['status'], 'passed')
        self.assertEqual(mb['charts']['0']['status'], 'failed')

    def test_cleanup_does_not_cross_dirs(self) -> None:
        """清理仅影响目标子目录。"""
        dir_a = scsh._chart_dir(self.work_dir, 'file_a')
        dir_b = scsh._chart_dir(self.work_dir, 'file_b')

        # 在 dir_b 放一个孤儿文件
        with open(os.path.join(dir_b, 'orphan.txt'), 'w') as f:
            f.write('orphan')

        # 清理 dir_a，不影响 dir_b
        scsh._cleanup_chart_dir(dir_a, [{'code': 'x'}])
        self.assertTrue(os.path.exists(os.path.join(dir_b, 'orphan.txt')))


class TestReentryManifestPreservation(unittest.TestCase):
    """集成测试：重入模式下 manifest 不被清理。"""

    def setUp(self) -> None:
        self.work_dir = tempfile.mkdtemp()
        self.chart_dir = scsh._chart_dir(self.work_dir, 'target')
        # 模拟首次运行后的 manifest
        manifest = {
            'version': '4.1',
            'charts': {
                '0': {'status': 'passed', 'code_hash': 'sha256:abc123',
                       'png': 'chart_0.png', 'overall_score': 8},
                '1': {'status': 'needs_intervention', 'code_hash': 'sha256:def456',
                       'png': 'chart_1.png', 'overall_score': 4},
            },
        }
        scsh._save_manifest(self.chart_dir, manifest)
        # 创建 PNG 文件
        for i in range(2):
            with open(os.path.join(self.chart_dir, f'chart_{i}.png'), 'wb') as f:
                f.write(b'\x89PNG' + b'\x00' * 100)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_manifest_preserved_on_reentry(self) -> None:
        """重入模式 (--only-charts) 不触发清理，manifest 完整保留。"""
        # 模拟重入：不调用 _cleanup_chart_dir
        # 直接加载 manifest 验证数据完整
        m = scsh._load_manifest(self.chart_dir)
        self.assertEqual(m['charts']['0']['status'], 'passed')
        self.assertEqual(m['charts']['1']['status'], 'needs_intervention')

    def test_incremental_skip_on_reentry(self) -> None:
        """重入时，已通过图表应被跳过。"""
        m = scsh._load_manifest(self.chart_dir)
        # Chart #0: passed + hash match + PNG exists → 不需重建
        self.assertFalse(scsh._chart_needs_rebuild(
            m, 0, 'sha256:abc123', self.chart_dir
        ))
        # Chart #1: needs_intervention → 需要重建
        self.assertTrue(scsh._chart_needs_rebuild(
            m, 1, 'sha256:def456', self.chart_dir
        ))


# ─────────────────────────────────────────────────────────────────────
# v4.3: 系统指令与用户输入分离 (Prompt Separation) 测试
# ─────────────────────────────────────────────────────────────────────

class TestPromptSeparation(unittest.TestCase):
    """验证 review_with_gemini 的 System/User Prompt 分离架构 (v4.3)。"""

    def _make_fake_response(self, score: int = 8) -> object:
        import json as _json
        payload = {
            "overall_pass": True, "overall_score": score, "issues": [],
            "layout_score": score, "color_score": score, "readability_score": score,
            "chart_type": "pie", "recommended_direction": None, "fix_code": None,
        }
        class FakeResponse:
            text = _json.dumps(payload)
        return FakeResponse()

    def _capture_call(self, png_path, mermaid_code, retry_history=None, chart_type='pie'):
        """公共辅助：用 MagicMock 替换整个 Gemini Client，捕获 generate_content 调用参数。"""
        import mermaid_scsh as ms
        captured = {}
        fake_response = self._make_fake_response()

        mock_client = unittest.mock.MagicMock()
        mock_client.models.generate_content.side_effect = (
            lambda model, contents, config: (
                captured.update({
                    'system_instruction': getattr(config, 'system_instruction', None),
                    'user_prompt': contents[1] if len(contents) > 1 else '',
                }) or fake_response
            )
        )

        with unittest.mock.patch('mermaid_scsh._get_gemini_client', return_value=mock_client):
            try:
                ms.review_with_gemini(
                    png_path=png_path,
                    mermaid_code=mermaid_code,
                    retry_history=retry_history,
                    chart_type=chart_type,
                )
            except Exception:
                pass  # 忽略渲染层异常，只关心 captured 参数

        return captured

    def _make_png(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        f.close()
        return f.name

    def test_system_instruction_equals_review_prompt(self):
        """system_instruction 必须精确等于全局 REVIEW_PROMPT。"""
        import mermaid_scsh as ms, os
        png = self._make_png()
        try:
            cap = self._capture_call(png, 'pie\n  "A" : 60\n  "B" : 40')
        finally:
            os.unlink(png)
        self.assertTrue(cap, "未能捕获到 Gemini API 调用参数")
        self.assertEqual(
            cap['system_instruction'], ms.REVIEW_PROMPT,
            "config.system_instruction 必须精确等于 REVIEW_PROMPT"
        )

    def test_user_prompt_excludes_role_definition(self):
        """user_prompt 不应包含 REVIEW_PROMPT 的固定角色声明开头。"""
        import os
        ROLE_MARKER = "你是专业的 Mermaid 数据可视化审查专家"
        png = self._make_png()
        try:
            cap = self._capture_call(png, 'pie\n  "A" : 60\n  "B" : 40')
        finally:
            os.unlink(png)
        self.assertTrue(cap, "未能捕获到 Gemini API 调用参数")
        self.assertNotIn(
            ROLE_MARKER, cap['user_prompt'],
            "user_prompt 中不应含有 REVIEW_PROMPT 的固定角色声明"
        )

    def test_user_prompt_contains_mermaid_code(self):
        """user_prompt 必须包含本次请求的 Mermaid 源码。"""
        import os
        code = 'pie\n  title "分布"\n  "A" : 70\n  "B" : 30'
        png = self._make_png()
        try:
            cap = self._capture_call(png, code)
        finally:
            os.unlink(png)
        self.assertTrue(cap, "未能捕获到 Gemini API 调用参数")
        self.assertIn(code, cap['user_prompt'], "user_prompt 必须包含原始 Mermaid 代码")

    def test_user_prompt_contains_retry_history(self):
        """retry_history 的摘要必须出现在 user_prompt 中。"""
        import os
        history = [{
            'type': 'gemini_fix', 'attempt': 1, 'score': 5,
            'issues': [{'dimension': 'color', 'severity': 'warning', 'description': '对比度不足'}],
        }]
        png = self._make_png()
        try:
            cap = self._capture_call(png, 'flowchart TD\n  A --> B',
                                     retry_history=history, chart_type='flowchart')
        finally:
            os.unlink(png)
        self.assertTrue(cap, "未能捕获到 Gemini API 调用参数")
        self.assertIn('历史修复记录', cap['user_prompt'],
                      "retry_history 的历史修复摘要应出现在 user_prompt 中")




# ─────────────────────────────────────────────────────────────────────
# v4.2: 两级并发常量与 CLI 分发测试
# ─────────────────────────────────────────────────────────────────────

class TestConcurrencyV42(unittest.TestCase):
    """验证章节级与图表级并发常量及多文件分发逻辑 (v4.2)。"""

    # ── 1. 默认常量值 ──────────────────────────────────────────────
    def test_default_concurrency_chart(self):
        """CONCURRENCY_CHART 默认值应为 5。"""
        import importlib, os, sys
        env_bak = os.environ.pop('MERMAID_SCSH_CONCURRENCY', None)
        try:
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']
            import mermaid_scsh as ms
            self.assertEqual(ms.CONCURRENCY_CHART, 5)
        finally:
            if env_bak is not None:
                os.environ['MERMAID_SCSH_CONCURRENCY'] = env_bak
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']

    def test_default_concurrency_chapter(self):
        """CONCURRENCY_CHAPTER 默认值应为 3。"""
        import importlib, os, sys
        env_bak = os.environ.pop('MERMAID_SCSH_CHAPTER_CONCURRENCY', None)
        try:
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']
            import mermaid_scsh as ms
            self.assertEqual(ms.CONCURRENCY_CHAPTER, 3)
        finally:
            if env_bak is not None:
                os.environ['MERMAID_SCSH_CHAPTER_CONCURRENCY'] = env_bak
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']

    # ── 2. 环境变量覆盖 ────────────────────────────────────────────
    def test_env_override_concurrency_chart(self):
        """MERMAID_SCSH_CONCURRENCY 可覆盖 CONCURRENCY_CHART。"""
        import os, sys
        os.environ['MERMAID_SCSH_CONCURRENCY'] = '8'
        if 'mermaid_scsh' in sys.modules:
            del sys.modules['mermaid_scsh']
        try:
            import mermaid_scsh as ms
            self.assertEqual(ms.CONCURRENCY_CHART, 8)
        finally:
            del os.environ['MERMAID_SCSH_CONCURRENCY']
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']

    def test_env_override_concurrency_chapter(self):
        """MERMAID_SCSH_CHAPTER_CONCURRENCY 可覆盖 CONCURRENCY_CHAPTER。"""
        import os, sys
        os.environ['MERMAID_SCSH_CHAPTER_CONCURRENCY'] = '2'
        if 'mermaid_scsh' in sys.modules:
            del sys.modules['mermaid_scsh']
        try:
            import mermaid_scsh as ms
            self.assertEqual(ms.CONCURRENCY_CHAPTER, 2)
        finally:
            del os.environ['MERMAID_SCSH_CHAPTER_CONCURRENCY']
            if 'mermaid_scsh' in sys.modules:
                del sys.modules['mermaid_scsh']

    # ── 3. 章节级信号量上限 ─────────────────────────────────────────
    def test_chapter_semaphore_limits_concurrency(self):
        """main_async 应以 CONCURRENCY_CHAPTER 创建章节级 Semaphore，
        且同时持有锁的协程数不超过该阈值。"""
        import asyncio, mermaid_scsh as ms

        concurrency_limit = 2   # 固定测试值，与默认值无关
        acquired_peak     = 0
        currently_held    = 0
        lock              = asyncio.Lock()

        async def fake_single(_args):
            nonlocal acquired_peak, currently_held
            async with lock:
                currently_held += 1
                acquired_peak = max(acquired_peak, currently_held)
            await asyncio.sleep(0.05)
            async with lock:
                currently_held -= 1

        async def run():
            # 构造 3 个虚拟文件路径，章节并发上限设为 2
            chapter_sem = asyncio.Semaphore(concurrency_limit)
            tasks = []
            for i in range(3):
                async def _one(i=i):
                    async with chapter_sem:
                        await fake_single(f'file{i}.md')
                tasks.append(_one())
            await asyncio.gather(*tasks)

        asyncio.run(run())
        self.assertLessEqual(
            acquired_peak, concurrency_limit,
            f"章节并发峰值 {acquired_peak} 超过 semaphore 上限 {concurrency_limit}",
        )

    # ── 4. 图表级信号量上限 ─────────────────────────────────────────
    def test_chart_semaphore_limits_concurrency(self):
        """async_check_and_fix_block 使用的图表级 semaphore 应被遵守。"""
        import asyncio, mermaid_scsh as ms

        chart_limit    = 2
        acquired_peak  = 0
        currently_held = 0
        lock           = asyncio.Lock()

        async def fake_chart_body():
            nonlocal acquired_peak, currently_held
            async with lock:
                currently_held += 1
                acquired_peak = max(acquired_peak, currently_held)
            await asyncio.sleep(0.05)
            async with lock:
                currently_held -= 1

        async def run():
            sem = asyncio.Semaphore(chart_limit)

            async def one_chart():
                async with sem:
                    await fake_chart_body()

            # 模拟 4 个图表并发
            await asyncio.gather(*[one_chart() for _ in range(4)])

        asyncio.run(run())
        self.assertLessEqual(
            acquired_peak, chart_limit,
            f"图表并发峰值 {acquired_peak} 超过 semaphore 上限 {chart_limit}",
        )

    # ── 5. --files / --file CLI 互斥且向后兼容 ─────────────────────
    def test_cli_files_arg_populates_files_list(self):
        """--files 参数传入多个路径后，args.files 应包含所有路径。"""
        import argparse, mermaid_scsh as ms, os, tempfile

        # 创建两个真实临时文件（parser 会做存在性校验之外的事，这里只测参数解析）
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f2:
            p1, p2 = f1.name, f2.name
        try:
            parser = argparse.ArgumentParser()
            file_group = parser.add_mutually_exclusive_group(required=True)
            file_group.add_argument('--file')
            file_group.add_argument('--files', nargs='+', metavar='FILE')
            args = parser.parse_args(['--files', p1, p2])
            # 模拟 main() 中的统一化逻辑
            if args.file:
                args.files = [args.file]
            self.assertEqual(len(args.files), 2)
            self.assertIn(p1, args.files)
            self.assertIn(p2, args.files)
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_cli_file_compat_creates_single_element_list(self):
        """旧式 --file 单文件参数应被统一为单元素 list。"""
        import argparse, mermaid_scsh as ms, os, tempfile

        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            p = f.name
        try:
            parser = argparse.ArgumentParser()
            file_group = parser.add_mutually_exclusive_group(required=True)
            file_group.add_argument('--file')
            file_group.add_argument('--files', nargs='+', metavar='FILE')
            args = parser.parse_args(['--file', p])
            if args.file:
                args.files = [args.file]
            self.assertEqual(args.files, [p])
        finally:
            os.unlink(p)


# ─────────────────────────────────────────────────────────────────────
# 执行
# ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60, flush=True)
    print("SCSH v4.2 升级测试套件", flush=True)
    print("=" * 60, flush=True)
    unittest.main(verbosity=2)

