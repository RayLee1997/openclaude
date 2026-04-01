#!/usr/bin/env python3
"""SCSH 边缘情况与回滚机制测试套件。

覆盖最新修复的功能点：
  - 如果在第2次及以后的修复尝试中发生语法错误（渲染崩溃），能捕获异常并回滚到最佳版本。
  - apply_fixes_to_markdown 能够处理 status='failed' 但带有有效回滚 code 的情况。
"""

import os
import sys
import unittest
import tempfile
import shutil
import asyncio

# 确保能 import mermaid_scsh（同目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mermaid_scsh as scsh

class AsyncMock(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chart_dir = scsh._chart_dir(self.tmpdir, 'test')
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

class TestScshRollbackMechanism(AsyncMock):
    def test_rollback_on_syntax_error(self):
        """测试在第二次修复时发生渲染错误是否能正确回滚。"""
        # 保存原本的依赖
        orig_render = scsh.render_mermaid_block
        orig_review = scsh.review_with_gemini
        orig_sanitize = scsh.l1_sanitize

        try:
            # 模拟渲染鸭子类型
            def mock_render(code, index, work_dir, file_stem=''):
                os.makedirs(work_dir, exist_ok=True)
                png_path = os.path.join(work_dir, 'dummy.png')
                with open(png_path, 'wb') as f:
                    f.write(b'dummy_image_data_more_than_5000_bytes' * 200)

                if "original" in code:
                    return {'success': True, 'png_path': png_path, 'stderr': '', 'returncode': 0, 'error_type': None}
                if "syntax error" in code:
                    return {'success': False, 'png_path': None, 'stderr': 'Parse error', 'returncode': 1, 'error_type': 'syntax_error'}
                return {'success': True, 'png_path': png_path, 'stderr': '', 'returncode': 0, 'error_type': None}
            
            # 模拟审查鸭子类型
            def mock_review(png_path, mermaid_code, retry_history=None, chart_type=''):
                if "original" in mermaid_code:
                    return {
                        'overall_score': 6,
                        'overall_pass': False,
                        'fix_code': 'graph TD\n    A("syntax error") --'
                    }
                return {'overall_pass': True, 'overall_score': 10}

            scsh.render_mermaid_block = mock_render
            scsh.review_with_gemini = mock_review
            scsh.l1_sanitize = lambda x: x

            block = {
                'code': 'graph TD\n    A("original code") --> B',
                'heading': 'Test',
                'chart_type': 'flowchart',
                'start_pos': 0,
                'end_pos': 100
            }
            
            result = scsh.check_and_fix_block(
                block, index=0, work_dir=self.tmpdir, max_retries=2
            )
            
            self.assertEqual(result['status'], 'needs_intervention')
            self.assertIn("original code", result['code'])
            self.assertEqual(result['score'], 6)
        finally:
            # 恢复
            scsh.render_mermaid_block = orig_render
            scsh.review_with_gemini = orig_review
            scsh.l1_sanitize = orig_sanitize

    def test_apply_fixes_failed_with_best_code(self):
        """测试 apply_fixes_to_markdown 当 status 为 failed 时，如果 code 有变动也能回写。"""
        md_content = "```mermaid\ngraph TD\n    A --> B\n```"
        blocks = [{'code': 'graph TD\n    A --> B', 'start_pos': 0, 'end_pos': len(md_content)}]
        
        # 结果是 failed，但是提供了一个更好的修复代码
        results = [{'status': 'failed', 'code': 'graph TD\n    A("better code") --> B', 'score': -1}]
        
        new_md = scsh.apply_fixes_to_markdown(md_content, blocks, results)
        self.assertIn("better code", new_md)
        self.assertNotIn("A --> B\n```", new_md)

class TestSafeResponseText(unittest.TestCase):
    def test_safe_response_text_valid(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.candidates = [MagicMock()]
        response.candidates[0].content.parts = [MagicMock()]
        response.candidates[0].content.parts[0].text = "valid text"
        
        self.assertEqual(scsh._safe_response_text(response), "valid text")
        
    def test_safe_response_text_empty_candidates(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.candidates = []
        response.prompt_feedback = "SAFETY_FILTER"
        
        with self.assertRaisesRegex(scsh.APIError, "Empty candidates"):
            scsh._safe_response_text(response)

    def test_safe_response_text_no_content(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.candidates = [MagicMock()]
        response.candidates[0].content = None
        response.candidates[0].finish_reason = "MAX_TOKENS"
        
        with self.assertRaisesRegex(scsh.APIError, "No content"):
            scsh._safe_response_text(response)

    def test_safe_response_text_empty_parts(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.candidates = [MagicMock()]
        response.candidates[0].content.parts = []
        response.candidates[0].finish_reason = "STOP"
        
        with self.assertRaisesRegex(scsh.APIError, "Empty parts"):
            scsh._safe_response_text(response)

if __name__ == '__main__':
    unittest.main()
