"""Typed resource identities; historical layouts never become new defaults."""
from copy import deepcopy
from uuid import UUID
from appointment_system.google_workspace import event_id
from .grants import GrantTransfer
from .records import private_reference
from .source import ConversionError
from .calendar import events

class ResourceTransfer:
 def __init__(self,grants):
  if not isinstance(grants,GrantTransfer):raise ConversionError('legacy_resource_configuration_invalid')
  self.grants=grants;self.installation=grants.installation

 def source(self,layout,source,table):
  rows=source.get(layout.schema+'.'+table,[])
  if type(rows) is not list:raise ConversionError('legacy_resource_source_invalid')
  return rows

 def permission(self,layout,source,record):
  matches=[row for row in self.source(layout,source,'google_connections') if row['role']==record['role']
           and row['subject']==record['subject'] and row['client_id']==record['client_id']]
  if len(matches)!=1:raise ConversionError('legacy_workbook_permission_unresolved')
  converted=self.grants.full_grant(matches[0])['google_resource_grants'][0]
  resource='client_sheet' if record['role']=='client' else 'agency_sheet'
  if resource not in converted['resources']:raise ConversionError('legacy_workbook_permission_unresolved')
  return matches[0],converted['id']

 def volume(self,layout,source,row):
  original,grant=self.permission(layout,source,row)
  layout_version=row.get('layout_version',1)
  if type(layout_version) is not int or layout_version not in (1,2):raise ConversionError('legacy_workbook_layout_invalid')
  result={key:deepcopy(row[key]) for key in ('role','subject','client_id','intent','spreadsheet_id','state')}
  result.update(volume_number=row.get('volume_number',1),layout_version=layout_version,grant_id=grant,
   generation=row.get('generation') or private_reference(self.installation.installation_id,'legacy-workbook-generation',str(row['intent'])),
   created_at=row.get('created_at') or original['connected_at'],workbook_protocol='legacy-sarsa-workbook-v'+str(layout_version))
  if type(result['volume_number']) is not int or result['volume_number']<1:raise ConversionError('legacy_workbook_volume_invalid')
  UUID(str(result['intent']));UUID(str(result['generation']))
  if result['state']!='creating' and not result['spreadsheet_id']:raise ConversionError('legacy_workbook_file_missing')
  return result

 def rows(self,layout,source,table,rows):
  result=[];jobs=self.source(layout,source,'delivery_jobs' if table=='sheet_rows' else 'enquiry_delivery_jobs')
  for row in rows:
   if row['role'] not in ('client','agency'):raise ConversionError('legacy_workbook_role_invalid')
   job=[value for value in jobs if value['id']==row['job_id']]
   if len(job)!=1:raise ConversionError('legacy_workbook_job_missing')
   expected='client_sheet' if row['role']=='client' else 'agency_sheet'
   if (table=='sheet_rows' and (job[0]['kind']!='sheet_booking' or job[0]['recipient_role']!=expected)
       or table=='enquiry_sheet_rows' and job[0]['kind']!=expected):raise ConversionError('legacy_workbook_job_mismatch')
   values=row['values_json']
   if (type(values) is not list or len(values) not in ((12,) if table=='sheet_rows' else (10,12))
       or any(type(value) is not str or len(value)>4000 for value in values)
       or values[0]!='004-sarsa-jyotish-sansthan' or values[1]!=row['job_id']
       or values[2]!=job[0]['booking_id' if table=='sheet_rows' else 'request_id']
       or (table=='sheet_rows' and values[3]!=str(job[0]['booking_revision']))):
    raise ConversionError('legacy_workbook_row_mismatch')
   result.append(deepcopy(row)|{'volume_number':row.get('volume_number',1)})
  return {table:result}

 def __call__(self,layout,table,rows,source=None):
  if table in ('google_connection','google_connections','sheet_owner_grants'):
   return self.grants(layout,table,rows,source)
  if layout.project=='003' and table in ('booking_calendar_events','booking_event_revisions') and type(source) is dict:
   return {'meeting_events':events(self.installation,layout,table,rows,source)}
  if layout.project!='004' or type(source) is not dict:raise ConversionError('legacy_resource_table_unprepared')
  if table=='google_workbooks':
   active=[];volumes=[];old_volumes=self.source(layout,source,'google_workbook_volumes')
   for row in rows:
    permission,_=self.permission(layout,source,row)
    value=deepcopy(row);value.update(lease=None,lease_until=None,volume_number=row.get('volume_number',1),
      layout_version=row.get('layout_version',1),connection_revision=permission['revision'],
      creation_attempt_at=row.get('creation_attempt_at') or (permission['connected_at'] if row['state']=='creating' else None))
    active.append(value)
    if not old_volumes:volumes.append(self.volume(layout,source,row))
    elif len([v for v in old_volumes if v['role']==row['role'] and v['volume_number']==value['volume_number']
      and all(v[field]==row[field] for field in ('intent','subject','client_id','spreadsheet_id','layout_version'))])!=1:
     raise ConversionError('legacy_workbook_active_volume_mismatch')
   return {'google_workbooks':active,'google_workbook_volumes':volumes}
  if table=='google_workbook_volumes':return {table:[self.volume(layout,source,row) for row in rows]}
  if table in ('sheet_rows','enquiry_sheet_rows'):return self.rows(layout,source,table,rows)
  if table=='meeting_events':
   bookings={row['id']:row for row in self.source(layout,source,'bookings')}
   for row in rows:
    if (row['booking_id'] not in bookings or row['booking_revision']>bookings[row['booking_id']]['revision']
        or row['event_id']!=event_id(row['booking_id'],row['booking_revision'],'legacy-sarsa004')):
     raise ConversionError('legacy_calendar_event_mismatch')
   return {table:deepcopy(rows)}
  raise ConversionError('legacy_resource_table_unprepared')
