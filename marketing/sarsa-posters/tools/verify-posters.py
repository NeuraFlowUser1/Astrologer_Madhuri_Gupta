"""Verify the committed native asset archive and current clickable PDFs."""
from io import BytesIO
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit
import hashlib,json,re
import numpy as np
import pymupdf
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent


def pixels(first,second):
    assert first.size==second.size
    assert np.array_equal(np.asarray(first.convert('RGB')),np.asarray(second.convert('RGB')))


def page_check(page,image,expected):
    assert tuple(page.rect)==(0,0,image.width,image.height)
    images=page.get_images(full=True)
    assert len(images)==1 and images[0][1]==0
    assert not page.get_fonts() and not page.get_text() and not page.get_drawings()
    embedded=Image.open(BytesIO(page.parent.extract_image(images[0][0])['image']))
    pixels(image,embedded)
    pixmap=page.get_pixmap(alpha=False)
    pixels(image,Image.frombytes('RGB',(pixmap.width,pixmap.height),pixmap.samples))
    links=page.get_links()
    assert len(links)==len(expected)==17
    for actual,wanted in zip(links,expected):
        assert actual['kind']==pymupdf.LINK_URI and actual['uri']==wanted['url']
        assert tuple(actual['from'])==tuple(wanted['rect'])
        assert page.rect.contains(actual['from'])
        assert page.parent.xref_get_key(actual['xref'],'Border')[1]=='[0 0 0]'
    for index,link in enumerate(links):
        for other in links[index+1:]:
            assert (link['from']&other['from']).get_area()==0


class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.values=[]
    def handle_starttag(self,tag,attributes):
        self.values.extend(v for k,v in attributes if k in ('href','src') and v)


def main():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for asset in manifest['files']:
        path=ROOT/asset['path']
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size==asset['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256']
    results=[]
    for variant in manifest['variants']:
        image=Image.open(ROOT/variant['image'])
        assert image.mode=='RGB' and list(image.size)==variant['nativeSize']==[941,1672]
        assert 1.70<=image.height/image.width<=1.80
        with pymupdf.open(ROOT/variant['pdf']) as document:
            assert len(document)==1
            page_check(document[0],image,variant['links'])
        results.append({'key':variant['key'],'nativeSize':list(image.size),'heightWidthRatio':image.height/image.width,
                        'links':17,'imageCount':1,'fontCount':0,'textCharacters':0,
                        'pixelEquality':True,'invisibleNonOverlappingLinks':True})
    with pymupdf.open(ROOT/manifest['comparisonPdf']) as document:
        assert len(document)==3
        for page,variant in zip(document,manifest['variants']):
            page_check(page,Image.open(ROOT/variant['image']),variant['links'])

    app=ROOT.parent.parent
    config=json.loads((app/'vercel.json').read_text())
    exclusions=config['functions']['api/index.py']['excludeFiles']
    assert 'marketing/**' in exclusions and 'appointment-system' not in exclusions and 'appointment-settings' not in exclusions
    receipt={'date':'2026-10-24','passed':True,'archiveAssets':len(manifest['files']),
             'archiveBytes':sum(v['bytes'] for v in manifest['files']),
             'allArchiveHashesMatch':True,'externalPixelChanges':[],
             'variants':results,'comparisonPages':3,'apiBundleExcludesMarketing':True,
             'providerCalls':0,'customerActions':0,'fullApplicationSuiteRun':False}
    out=ROOT/'verification.json'
    out.write_text(json.dumps(receipt,indent=2)+'\n')
    missing=[];count=0
    for path in sorted(ROOT.rglob('*')):
        if path.suffix=='.html':
            parser=Links();parser.feed(path.read_text());values=parser.values
        elif path.suffix=='.md':
            values=re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text())
        else:continue
        for value in values:
            parsed=urlsplit(value.strip('<>'))
            if parsed.scheme or parsed.netloc or not parsed.path:continue
            target=(path.parent/unquote(parsed.path)).resolve();count+=1
            if not target.exists():missing.append({'source':str(path.relative_to(ROOT)),'target':value})
    receipt.update({'localLinks':count,'missingLinks':missing,'passed':not missing})
    out.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    assert not missing


if __name__=='__main__':main()
