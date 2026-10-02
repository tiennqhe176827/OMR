"""Build CV1239 template from inspected PDF vector circles and a page render.
Run after exporting geometry.json/page.png with pdfplumber (page 1, 200 dpi).
"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/src/main/python'))
from omr.calibration import new_template, rect_normalized
from omr.coordinate_system import transform_points
from omr.perspective import homography_from_corners, warp_sheet
from omr.template_loader import save_template, file_sha256
from omr.visualization import draw_template
from omr.marker_detection import detect_markers, select_corner_markers
from omr.illumination import normalize_illumination

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'output/new-template'
data = json.loads((source / 'geometry.json').read_text(encoding='utf-8'))
image = cv2.imread(str(source / 'page.png'))
size = (1600, 2240)
scale = np.array([image.shape[1] / data['width'], image.shape[0] / data['height']])
squares = [r for r in data['rects'] if 9 < r['width'] < 12 and 9 < r['height'] < 12]
points = np.array([[r['x0']+r['width']/2, r['top']+r['height']/2] for r in squares])
left, right = sorted(points[points[:,0]<100], key=lambda p:p[1]), sorted(points[points[:,0]>500], key=lambda p:p[1])
corners = np.array([left[0], right[0], right[-1], left[-1]]) * scale
destination = np.array([[120,110],[1480,110],[1480,2130],[120,2130]], np.float32)
corners = select_corner_markers(detect_markers(image), image.shape)
matrix = homography_from_corners(corners, destination)
canonical = warp_sheet(image, matrix, size)
template = new_template('thpt_cv1239_4digit_v1',size,'THPT CV1239 blank PDF: 8-digit candidate ID and 4-digit exam code')
template.update(calibration_status='experimental', baseline_policy='blank_reference',
 calibration_notes='Measured from supplied blank PDF vector geometry; validated on rendered and synthetic camera scenes. Real printed camera scans still need verification.')
template['sbd']['num_columns'],template['ma_de']['num_columns']=8,4
template['markers']['corners']=(destination/size).tolist()
aux=np.array(left[1:-1]+right[1:-1])*scale
template['markers']['auxiliary']=(transform_points(aux,matrix)/size).tolist()
circles = [r for r in data['curves'] if 7.5<r['width']<8.1 and 7.1<r['height']<8.1
           and r.get('stroking_color') == [0.0,1.0,0.6,0.0]]
used=set()
def bubble(symbol,seed):
 candidates=[(np.linalg.norm(np.array([r['x0']+r['width']/2,r['top']+r['height']/2])-seed),i,r) for i,r in enumerate(circles)]
 distance,i,r=min(candidates,key=lambda p:p[0])
 if distance>1.2 or i in used: raise ValueError(f'Missing or reused PDF circle at {seed}: {distance}')
 used.add(i)
 center=np.array([r['x0']+r['width']/2,r['top']+r['height']/2])*scale
 radius=min(r['width'],r['height'])/2
 transformed=transform_points([center,center+[radius*scale[0],0],center+[0,radius*scale[1]]],matrix)
 rad=min(np.linalg.norm(transformed[1]-transformed[0]),np.linalg.norm(transformed[2]-transformed[0]))
 return {'symbol':symbol,'cx':float(transformed[0,0]/size[0]),'cy':float(transformed[0,1]/size[1]),'radius':float(rad/min(size))}
def install(name,blocks):
 bounds=[]
 for block in blocks:
  pts=np.array([[b['cx']*size[0],b['cy']*size[1]] for g in block['groups'] for b in g['bubbles']])
  lo=np.floor(pts.min(axis=0)-25);hi=np.ceil(pts.max(axis=0)+25)
  bounds.append((lo,hi))
 low=np.min([a for a,b in bounds],axis=0)-2;high=np.max([b for a,b in bounds],axis=0)+2
 extent=high-low
 template['regions'][name]=rect_normalized((*low,*extent),size)
 for block,(lo,hi) in zip(blocks,bounds):block['rect']=rect_normalized((*(lo-low),*(hi-lo)),extent)
 template[name]['blocks']=blocks
for name,cols,starts,prefix in [('sbd',8,[409.675,420.425,431.284,442.141,452.999,463.856,474.714,485.571],'SBD'),('ma_de',4,[507.093,517.951,528.809,539.667],'MD')]:
 groups=[{'id':f'{prefix}:C{c+1}','column':c+1,'bubbles':[bubble(str(r),(starts[c],101.69+r*15.6975)) for r in range(10)]} for c in range(cols)]
 install(name,[{'id':'columns','groups':groups}])
blocks=[]
for index,start in enumerate([78.7,205.0,331.3,457.6]):
 groups=[{'id':f'P1:Q{index*10+r+1}','question':index*10+r+1,'bubbles':[bubble(s,(start+c*22.3,303.48+r*13.44)) for c,s in enumerate('ABCD')]} for r in range(10)]
 blocks.append({'id':f'{index*10+1}_{index*10+10}','groups':groups})
install('phan_1',blocks)
blocks=[]
for index,start in enumerate([78.8,123.5,204.6,249.6,331.1,376.2,457.2,501.9]):
 q=index+1
 groups=[{'id':f'P2:Q{q}:{item}','question':q,'item':item,'bubbles':[bubble(s,(start+c*22.5,492.48+r*13.44)) for c,s in enumerate(['Dung','Sai'])]} for r,item in enumerate('abcd')]
 blocks.append({'id':f'question_{q}','groups':groups})
install('phan_2',blocks)
blocks=[]
for index,start in enumerate([75.75,156.38,237.0,317.63,398.26,478.89]):
 q=index+1;groups=[]
 for c in range(4):
  bubbles=[bubble(str(r),(start+c*13.4375,623.94+r*14.9825)) for r in range(10)]
  if c==0:bubbles.insert(0,bubble('-',(start,593.985)))
  if c in (1,2):bubbles.insert(0,bubble(',',(start+c*13.4375,608.965)))
  groups.append({'id':f'P3:Q{q}:C{c+1}','question':q,'column':c+1,'bubbles':bubbles})
 blocks.append({'id':f'question_{q}','groups':groups})
 template['phan_3']['questions'][str(q)]={'num_columns':4,'symbols':['-',',',*list('0123456789')],'symbol_rules':{'blank_policy':'trim_edges','minus':'-','decimal':',','digits':list('0123456789')}}
install('phan_3',blocks)
output=ROOT/'app/src/main/python/templates/thpt_cv1239_4digit.json'
reference=output.with_name('thpt_cv1239_4digit_reference.png')
cv2.imwrite(str(reference),normalize_illumination(canonical))
template['reference_image']=reference.name;template['reference_sha256']=file_sha256(reference)
save_template(output,template)
cv2.imwrite(str(source/'overlay.png'),draw_template(canonical,template,labels=False))
print('Bubbles:',len(used),'Auxiliary markers:',len(aux))
from omr.pipeline import process_exam_sheet
result,_=process_exam_sheet(image,str(output))
print(result['status'],result.get('error'))
