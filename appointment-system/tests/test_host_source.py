"""One contained hosting export, exact source inventory and no secret discovery."""
from pathlib import Path
import contextlib,io,json,runpy,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from tools.install.package import build,install,verify,PackageError
from tools.install.host import prepare as entry
from tools.install import source
from .fixtures import installation,business


class HostingSource(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
  self.master=self.root/'master';(self.master/'engine/appointment_system').mkdir(parents=True)
  (self.master/'engine/appointment_system/runtime.py').write_text('SYNTHETIC=1\n')
  (self.master/'engine/appointment_system/application.py').write_text('SYNTHETIC=1\n')
  (self.master/'requirements.txt').write_text('synthetic-package==1\n');build(self.master)
  self.project=self.root/'client';self.project.mkdir();subprocess.run(['git','init','-q',str(self.project)],check=True)
  settings=self.project/'appointment-settings';settings.mkdir()
  (settings/'project.json').write_text(json.dumps(installation()));(settings/'business-settings.json').write_text(json.dumps(business()))
  install(self.master,self.project,expected_root=self.project,installation_id=installation()['installation_id'],project_id=installation()['project_id'])
  entry(self.project,expected_root=self.project)
  for name,body in [('requirements.txt','-r appointment-system/requirements.txt\n'),('package.json','{}'),('vercel.json','{}'),('index.html','Synthetic website')]:
   (self.project/name).write_text(body)
  (self.project/'public').mkdir();(self.project/'public/Existing image.svg').write_text('<svg></svg>')
  self.names=sorted(source.REQUIRED|{'index.html','public/Existing image.svg'})
  self.manifest=self.project/source.MANIFEST;self.save()
  self.created=[];original=tempfile.mkdtemp
  def scoped(**kwargs):
   path=original(dir=self.root,**kwargs);self.created.append(Path(path));return path
  self.patch=patch.object(source.tempfile,'mkdtemp',side_effect=scoped);self.patch.start();self.addCleanup(self.patch.stop)

 def save(self,**changes):self.manifest.write_text(json.dumps({'version':1,'files':self.names}|changes))
 def run_export(self):return source.prepare(self.project,expected_root=self.project)

 def test_export_contains_every_engine_file_and_only_reviewed_website_files_after_source_removal(self):
  (self.project/'.env.production').write_text('SYNTHETIC_PRIVATE=not-for-export')
  (self.project/'unreviewed.txt').write_text('not approved')
  release=verify(self.project/'appointment-system');report=self.run_export();output=Path(report['destination'])
  shutil.rmtree(self.master);shutil.rmtree(self.project)
  self.assertEqual(verify(output/'appointment-system'),release);self.assertFalse(report['deployed'])
  self.assertFalse((output/'.env.production').exists());self.assertFalse((output/'unreviewed.txt').exists())
  self.assertEqual((output/'index.html').read_text(),'Synthetic website')
  self.assertEqual((output/'public/Existing image.svg').read_text(),'<svg></svg>')
  manifest=json.loads(Path(report['manifest']).read_text())
  self.assertEqual(report['files'],len(self.names)+1+len(release['files'])+1)
  self.assertEqual(manifest['release_digest'],release['content_digest']);self.assertNotIn('not-for-export',json.dumps(manifest))

 def test_missing_duplicate_private_and_traversing_paths_refuse_before_export(self):
  for names in (self.names[:-1],self.names+[self.names[0]],self.names+['../secret.txt'],
    self.names+['.env.production'],self.names+['private/key.json'],self.names+['client_secret_123.json'],
    self.names+['appointment-system/release.json'],self.names+['node_modules/helper.js']):
   with self.subTest(extra=names[-1]):
    self.save(files=names)
    with self.assertRaises((PackageError,OSError)):self.run_export()
  self.assertEqual(self.created,[])

 def test_links_or_an_old_entry_are_not_exported(self):
  index=self.project/'index.html';index.unlink();index.symlink_to(self.project/'package.json')
  with self.assertRaises(PackageError):self.run_export()
  self.assertTrue(all(not path.exists() for path in self.created));index.unlink();index.write_text('Synthetic')
  (self.project/'api/index.py').write_text('import old_backend\n')
  with self.assertRaises(PackageError):self.run_export()

 def test_changed_engine_manifest_is_rejected(self):
  (self.project/'appointment-system/engine/appointment_system/runtime.py').write_text('CHANGED=2\n')
  with self.assertRaises(PackageError):self.run_export()
  self.assertEqual(self.created,[])

 def test_a_valid_concurrent_package_upgrade_cannot_produce_a_mixed_export(self):
  original=source.copy_checked
  def upgrade(root,name,destination):
   result=original(root,name,destination)
   if name=='vercel.json':
    (root/'appointment-system/engine/appointment_system/runtime.py').write_text('UPGRADED=2\n')
    build(root/'appointment-system',release='1.0.0-rc.2')
   return result
  with patch.object(source,'copy_checked',side_effect=upgrade),self.assertRaisesRegex(PackageError,'changed'):
   self.run_export()
  self.assertFalse(self.created[0].exists())

 def test_command_outputs_only_the_prepared_result_and_redacts_configuration_errors(self):
  arguments=['source',str(self.project),'--expected-root',str(self.project)]
  output=io.StringIO()
  with patch.object(sys,'argv',arguments),contextlib.redirect_stdout(output):
   runpy.run_module('tools.install.source',run_name='__main__')
  self.assertFalse(json.loads(output.getvalue())['deployed'])
  (self.project/'appointment-settings/project.json').write_text('{"private":"synthetic-do-not-print"}')
  with patch.object(sys,'argv',arguments),self.assertRaises(SystemExit) as error:
   runpy.run_module('tools.install.source',run_name='__main__')
  self.assertNotIn('synthetic-do-not-print',str(error.exception));self.assertIn('preparation refused',str(error.exception))

 def test_editing_an_earlier_file_while_copying_removes_the_incomplete_export(self):
  original=source.copy_checked
  def change(root,name,destination):
   result=original(root,name,destination)
   if name=='vercel.json':(root/'index.html').write_text('Changed after its copy')
   return result
  with patch.object(source,'copy_checked',side_effect=change),self.assertRaisesRegex(PackageError,'changed'):
   self.run_export()
  self.assertEqual(len(self.created),1);self.assertFalse(self.created[0].exists())
  self.assertFalse(Path(str(self.created[0])+'.manifest.json').exists())

 def test_existing_report_is_never_overwritten_or_deleted_on_failure(self):
  original=source.copy_checked
  def collision(root,name,destination):
   result=original(root,name,destination)
   if name=='vercel.json':Path(str(destination)+'.manifest.json').write_text('Existing unrelated report')
   return result
  with patch.object(source,'copy_checked',side_effect=collision),self.assertRaises(FileExistsError):self.run_export()
  self.assertFalse(self.created[0].exists())
  self.assertEqual(Path(str(self.created[0])+'.manifest.json').read_text(),'Existing unrelated report')

 def test_foreign_root_duplicate_json_fields_and_wrong_manifest_version_refuse(self):
  with self.assertRaises(PackageError):source.prepare(self.project,expected_root=self.root)
  for text in ('{"version":1,"version":1,"files":[]}',json.dumps({'version':True,'files':self.names}),
    json.dumps({'version':1,'files':self.names,'unexpected':True})):
   self.manifest.write_text(text)
   with self.assertRaises(PackageError):self.run_export()
