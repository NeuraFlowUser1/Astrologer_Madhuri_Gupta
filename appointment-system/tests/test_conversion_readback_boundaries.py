"""Imported records must retain their exact identities and contents before cutover."""
import unittest
from unittest.mock import Mock,patch
from tools.conversion import verification as v
from tools.conversion.source import ConversionError

class ReadbackBoundaries(unittest.TestCase):
 def test_primary_identity_or_explicit_nullable_identity_is_required(self):
  connection=Mock();connection.execute.return_value.fetchall.return_value=[]
  with self.assertRaisesRegex(ConversionError,'identity_missing'):v.identity_fields(connection,'bookings')
  self.assertEqual(v.identity_fields(connection,'email_reservations'),['job_id','enquiry_job_id','verification_job_id'])
  for table in ['bookings;drop','Foreign',None]:
   with self.assertRaisesRegex(ConversionError,'verification_invalid'):v.identity_fields(connection,table)
  self.assertFalse(v.valid_key('bookings',['id'],{'id':None}));self.assertFalse(v.valid_key('bookings',['id'],{}))
  self.assertTrue(v.valid_key('email_reservations',['job_id','enquiry_job_id'],{'job_id':'one','enquiry_job_id':None}))
  self.assertFalse(v.valid_key('email_reservations',['job_id','enquiry_job_id'],{'job_id':'one','enquiry_job_id':'two'}))

 def test_large_readback_is_batched_without_losing_records_and_unbounded_record_is_refused(self):
  connection=Mock();connection.execute.return_value.fetchall.side_effect=[['a','b'],['c']]
  with patch.object(v,'MAX_BATCH',2):self.assertEqual(v.read(connection,'bookings',['id'],[{'id':1},{'id':2},{'id':3}]),['a','b','c'])
  self.assertEqual([len(call.args[1][0].obj) for call in connection.execute.call_args_list],[2,1])
  with patch.object(v,'MAX_BATCH_BYTES',16),self.assertRaisesRegex(ConversionError,'record_too_large'):v.read(connection,'bookings',['id'],[{'id':'x'*20}])

 def test_capture_refuses_missing_duplicate_reassigned_and_modified_records(self):
  connection=Mock();row={'id':'synthetic','state':'confirmed'}
  with patch.object(v,'identity_fields',return_value=['id']):
   for rows,error in [([{'state':'confirmed'}],'identity_missing'),([row,row],'duplicate_identity')]:
    with self.assertRaisesRegex(ConversionError,error):v.capture(connection,{'bookings':rows})
   for results,error in [([], 'missing_record'),([({'id':'other','state':'confirmed'},{'id':'other','state':'confirmed'})],'identity_changed'),([(row|{'state':'cancelled'},row)],'content_changed:bookings:state')]:
    with patch.object(v,'read',return_value=results),self.assertRaisesRegex(ConversionError,error):v.capture(connection,{'bookings':[row]})
   with patch.object(v,'read',return_value=[(row,row)]):
    manifest=v.capture(connection,{'bookings':[row],'empty_table':[]});self.assertEqual(manifest['bookings']['keys'],[{'id':'synthetic'}]);self.assertNotIn('empty_table',manifest)

 def test_invalid_or_changed_manifest_never_claims_verified_migration(self):
  connection=Mock();row={'id':'synthetic','state':'confirmed'};entry={'fields':['id'],'keys':[{'id':'synthetic'}],'count':1,'sha256':v.fingerprint([row])}
  with patch.object(v,'identity_fields',return_value=['id']),patch.object(v,'read',return_value=[(row,row)]) as read:
   self.assertEqual(len(v.verify(connection,{'bookings':entry})),64)
   for manifest in [None,{'bad;table':entry},{'bookings':entry|{'count':True}},{'bookings':entry|{'keys':[{}]}},{'bookings':entry|{'fields':['other']}},{'bookings':entry|{'keys':[{'id':'synthetic'}]*2,'count':2}}]:
    with self.subTest(manifest=manifest),self.assertRaisesRegex(ConversionError,'verification_invalid'):v.verify(connection,manifest)
   read.return_value=[(row|{'state':'cancelled'},row)]
   with self.assertRaisesRegex(ConversionError,'content_changed'):v.verify(connection,{'bookings':entry})
