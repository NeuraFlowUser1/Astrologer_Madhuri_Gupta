"""Every supported historical layout is checked against actual native catalogues."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.conversion import source
from .legacy_store import LegacyTarget,TARGETS

class LayoutCatalogue(unittest.TestCase):
 def test_four_exact_reviewed_shapes_and_no_secret_or_factory_dependency(self):
  values=source.catalogue()
  self.assertEqual({item.identifier for item in values},set(TARGETS))
  self.assertEqual([(item.project,len(item.ledger)) for item in values],[('003',16),('003',40),('004',31),('004',52)])
  self.assertFalse(any('appointment_system.' in key for item in values for key in item.structure['relations']))
  retained=next(item for item in values if item.identifier=='legacy-004-31')
  self.assertEqual(len(retained.variants),1)
  self.assertEqual(retained.variants[0].ledger,retained.ledger)

 def test_tampered_digest_duplicate_fields_and_invalid_types_are_refused(self):
  original=json.loads(source.CATALOG.read_text())
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'catalogue.json'
   with patch.object(source,'CATALOG',path):
    with self.assertRaises(source.ConversionError):source.catalogue()
    for value in (original|{'version':True},original|{'layouts':[]},original|{'layouts':{}}):
     path.write_text(json.dumps(value))
     with self.assertRaises(source.ConversionError):source.catalogue()
    changed=json.loads(json.dumps(original));changed['layouts'][0]['structure_digest']='0'*64
    path.write_text(json.dumps(changed))
    with self.assertRaises(source.ConversionError):source.catalogue()
    path.write_text('{"version":1,"version":1,"layouts":[]}')
    with self.assertRaises(source.ConversionError):source.catalogue()

 def test_variant_cannot_change_an_unknown_function_skip_its_hash_or_repeat_an_identity(self):
  from copy import deepcopy
  original=json.loads(source.CATALOG.read_text())
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'catalogue.json'
   for mutation in ('digest','old-hash','new-hash','unknown-function','repeated-function','shape'):
    changed=deepcopy(original);layout=next(x for x in changed['layouts'] if x['identifier']=='legacy-004-31')
    variant=layout['function_variants'][0];replacement=variant['replacements'][0]
    if mutation=='digest':variant['structure_digest']='0'*64
    elif mutation=='old-hash':replacement[3]='0'*64
    elif mutation=='new-hash':replacement[4]='not-a-hash'
    elif mutation=='unknown-function':replacement[1]='unknown_function'
    elif mutation=='repeated-function':variant['replacements'].append(replacement[:])
    else:variant['extra']='unreviewed'
    path.write_text(json.dumps(changed))
    with self.subTest(mutation=mutation),patch.object(source,'CATALOG',path),self.assertRaises(source.ConversionError):
     source.catalogue()

@unittest.skipUnless(os.environ.get('BOOKING_LEGACY_SQL_PROOF')=='owned','Owned historical native layouts required.')
class NativeHistoricalLayouts(unittest.TestCase):
 def target(self,identifier):
  target=LegacyTarget(identifier);self.addCleanup(target.close);return target

 def test_all_four_actual_layouts_match_exactly_before_private_row_read(self):
  for identifier in TARGETS:
   with self.subTest(layout=identifier):
    target=self.target(identifier);layout=source.detect(target)
    self.assertEqual(layout.identifier,identifier)
    rows=source.read_rows(target,layout)
    self.assertEqual(set(rows),set(layout.structure['relations']))
    self.assertNotIn(layout.schema+'.schema_migrations',rows)

 def test_only_exact_reviewed_comment_removal_is_accepted_as_the_published_variant(self):
  from psycopg import sql
  target=self.target('legacy-004-31')
  names=('admit_checkout','claim_google_workbook','expire_holds','reserve_checkout')
  query="SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='sarsa_booking' AND p.proname=ANY(%s) ORDER BY p.proname"
  previous=dict(target.execute(query,(list(names),)).fetchall())
  patch_file=Path(__file__).parent/'legacy_schema/004/live-31-commentless-functions.sql'
  try:
   target.run(patch_file.read_text())
   published=dict(target.execute(query,(list(names),)).fetchall())
   for name in names:
    original=previous[name].splitlines();actual=published[name].splitlines()
    self.assertEqual(len(original),len(actual))
    for before,after in zip(original,actual):
     self.assertTrue(before==after or before.strip().startswith('--') and not after.strip(),name)
   layout=source.detect(target)
   base=next(x for x in source.catalogue() if x.identifier=='legacy-004-31')
   self.assertEqual(layout.digest,base.variants[0].digest)
   # Any further unreviewed change, even one with unchanged migration entries,
   # remains rejected. There is no general whitespace/comment normalization.
   target.run(published['expire_holds'].replace('DECLARE changed integer;','DECLARE changed bigint;')+';')
   with self.assertRaisesRegex(source.ConversionError,'legacy_structure_unrecognized'):source.detect(target)
  finally:
   for definition in previous.values():target.run(definition+';')
  self.assertEqual(source.detect(target).digest,base.digest)

 def test_read_adapter_accepts_read_ctes_but_database_refuses_hidden_writes(self):
  target=self.target('legacy-003-16')
  self.assertEqual(target.execute('WITH marker AS (SELECT 1 AS value) SELECT value FROM marker').fetchone(),(1,))
  with self.assertRaisesRegex(AssertionError,'Owned historical proof SQL failed'):
   target.execute('WITH changed AS (UPDATE public.bookings SET full_name=full_name RETURNING id) SELECT id FROM changed')
  self.assertEqual(source.detect(target).identifier,'legacy-003-16')

 def test_matching_ledger_cannot_hide_an_added_table_constraint_function_or_index(self):
  target=self.target('legacy-003-16')
  actions=[('CREATE TABLE public.unreviewed_business(id integer);','DROP TABLE public.unreviewed_business;'),
   ('ALTER TABLE public.bookings ADD CONSTRAINT unreviewed_rule CHECK (amount_paise>1);',
     'ALTER TABLE public.bookings DROP CONSTRAINT unreviewed_rule;'),
   ("CREATE FUNCTION public.unreviewed_logic() RETURNS boolean LANGUAGE sql AS 'SELECT true';",'DROP FUNCTION public.unreviewed_logic();'),
   ('CREATE INDEX unreviewed_index ON public.bookings(email);','DROP INDEX public.unreviewed_index;')]
  for change,restore in actions:
   with self.subTest(change=change.split()[1]):
    target.run(change)
    try:
     with self.assertRaisesRegex(source.ConversionError,'legacy_structure_unrecognized'):source.detect(target)
    finally:target.run(restore)
  self.assertEqual(source.detect(target).identifier,'legacy-003-16')

 def test_unchanged_schema_cannot_hide_rewritten_migration_hash(self):
  target=self.target('legacy-004-31');layout=source.detect(target);name,digest=next(iter(layout.ledger.items()))
  from psycopg import sql
  query=sql.SQL('UPDATE sarsa_booking.schema_migrations SET sha256={} WHERE version={};')
  target.run(query.format(sql.Literal('0'*64),sql.Literal(name)).as_string())
  try:
   with self.assertRaisesRegex(source.ConversionError,'legacy_migration_ledger_changed'):source.detect(target)
  finally:target.run(query.format(sql.Literal(digest),sql.Literal(name)).as_string())

 def test_matching_ledger_cannot_hide_disabled_removed_or_changed_triggers(self):
  from psycopg import sql
  target=self.target('legacy-004-31')
  schema,table,name,definition=target.execute("""SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid)
   FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='sarsa_booking' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname LIMIT 1"""
  ).fetchone()
  relation=sql.Identifier(schema,table);trigger=sql.Identifier(name)
  restore=sql.SQL('ALTER TABLE {} ENABLE TRIGGER {};').format(relation,trigger).as_string()
  for action in ('DISABLE','ENABLE REPLICA','ENABLE ALWAYS'):
   with self.subTest(action=action):
    target.run(sql.SQL('ALTER TABLE {} '+action+' TRIGGER {};').format(relation,trigger).as_string())
    try:
     with self.assertRaisesRegex(source.ConversionError,'legacy_structure_unrecognized'):source.detect(target)
    finally:target.run(restore)
  target.run(sql.SQL('DROP TRIGGER {} ON {};').format(trigger,relation).as_string())
  try:
   with self.assertRaisesRegex(source.ConversionError,'legacy_structure_unrecognized'):source.detect(target)
  finally:target.run(definition+';')
  # Timing is part of a trigger's behaviour even when its function is unchanged.
  self.assertIn('BEFORE',definition)
  target.run(sql.SQL('DROP TRIGGER {} ON {};').format(trigger,relation).as_string())
  target.run(definition.replace('BEFORE','AFTER',1)+';')
  try:
   with self.assertRaisesRegex(source.ConversionError,'legacy_structure_unrecognized'):source.detect(target)
  finally:
   target.run(sql.SQL('DROP TRIGGER {} ON {};').format(trigger,relation).as_string())
   target.run(definition+';')
  self.assertEqual(source.detect(target).identifier,'legacy-004-31')
