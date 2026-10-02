import json
import tempfile
import unittest
import cv2
import numpy as np
from test_camera_bridge import ROOT
from omr.template_loader import load_template
from omr.roi_extraction import iter_groups
from omr.pipeline import process_exam_sheet
from android_bridge import Scanner

TEMPLATE = ROOT / 'app/src/main/python/templates/thpt_cv1239_4digit.json'

class CV1239Tests(unittest.TestCase):
    def test_template_dimensions_and_switching(self):
        data = load_template(str(TEMPLATE)).data
        self.assertEqual(data['sbd']['num_columns'], 8)
        self.assertEqual(data['ma_de']['num_columns'], 4)
        self.assertEqual(sum(len(g['bubbles']) for _, _, g in iter_groups(data)), 602)
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory)
            scanner.pending_since_ns = 123
            scanner.set_template('cv1239')
            self.assertEqual(scanner.template_path, str(TEMPLATE))
            self.assertIsNone(scanner.pending_since_ns)
            scanner.set_template('current')
            self.assertIn('real_sheet_experimental', scanner.template_path)
            with self.assertRaises(ValueError): scanner.set_template('../../bad')

    def test_blank_pdf_and_marked_camera_variants(self):
        source = ROOT / 'output/new-template/page.png'
        if not source.exists(): self.skipTest('Source PDF page render unavailable')
        image = cv2.imread(str(source))
        data = load_template(str(TEMPLATE)).data
        result, _ = process_exam_sheet(image, str(TEMPLATE))
        self.assertEqual(result['status'], 'ok', result.get('error'))
        self.assertTrue(all(g['status'] == 'blank' for g in result['groups'].values()))
        matrix = np.asarray(result['alignment']['canonical_to_original'])
        size = np.array([data['canonical_size']['width'], data['canonical_size']['height']])
        answers = {'sbd':'01234567', 'ma_de':'0123'}
        short = ['-1,5','1,5','0','2108','0,31','9']
        expected = {}
        for region, _, group in iter_groups(data):
            if region in answers: value = answers[region][group['column']-1]
            elif region == 'phan_1': value = 'ABCD'[(group['question']-1)%4]
            elif region == 'phan_2': value = 'Dung' if group['item'] in 'ac' else 'Sai'
            else:
                text = short[group['question']-1]
                value = text[group['column']-1] if group['column'] <= len(text) else None
            expected[group['id']] = value
            if value is None: continue
            bubble = next(b for b in group['bubbles'] if b['symbol']==value)
            center = np.array([bubble['cx']*size[0], bubble['cy']*size[1], 1.])
            point = matrix @ center; point = point[:2]/point[2]
            radius = round(bubble['radius']*min(size)*image.shape[1]/size[0]*.85)
            cv2.circle(image, tuple(np.round(point).astype(int)), radius, (35,35,35), -1)
        h,w = image.shape[:2]
        transform = cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),
                                               np.float32([[100,60],[w+60,120],[w+90,h+60],[60,h+100]]))
        perspective = cv2.warpPerspective(image,transform,(w+180,h+180),borderValue=(40,40,40))
        variants = [image, perspective, cv2.resize(perspective, (1000,1400))]
        for index, scene in enumerate(variants):
            with self.subTest(scene=index):
                result, _ = process_exam_sheet(scene, str(TEMPLATE))
                self.assertEqual(result['status'], 'ok', result.get('error'))
                self.assertEqual(result['student']['so_bao_danh']['value'], answers['sbd'])
                self.assertEqual(result['student']['ma_de']['value'], answers['ma_de'])
                self.assertEqual([result['phan_3'][str(q)]['value'] for q in range(1,7)], short)
                for ident,value in expected.items():
                    self.assertEqual((result['groups'][ident]['status'], result['groups'][ident]['selected']),
                                     ('blank' if value is None else 'ok', value), ident)
