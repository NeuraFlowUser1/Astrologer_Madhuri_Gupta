"""Explicit non-record dispositions; spent allowance is handled separately.

Replacing old numeric limits does not reset stored reservation facts and does
not approve a new sending allowance. Retiring old ON metadata never enables
the fresh installation. Private records cannot take this no-record path.
"""
from .records import ConfigurationOnly,digest
from .source import ConversionError

class ConfigurationTransfer:
 def __call__(self,layout,table,rows,source=None):
  if table=='email_policy':
   expected={'id','daily_limit','monthly_limit','contact_daily_limit','contact_monthly_limit'}
   if (layout.project!='004' or len(rows)!=1 or set(rows[0])!=expected or rows[0]['id']!=1
       or any(type(rows[0][field]) is not int or rows[0][field]<0 for field in expected-{'id'})
       or rows[0]['contact_daily_limit']>rows[0]['daily_limit']
       or rows[0]['contact_monthly_limit']>rows[0]['monthly_limit']):
    raise ConversionError('legacy_configuration_invalid')
   return ConfigurationOnly(table,digest(rows),'historical_limits_replaced')
  if table=='product_state':
   if (len(rows)!=1 or rows[0].get('singleton') is not True or rows[0].get('project')!=layout.project
       or type(rows[0].get('enabled')) is not bool):raise ConversionError('legacy_configuration_invalid')
   return ConfigurationOnly(table,digest(rows),'historical_activation_retired')
  raise ConversionError('legacy_configuration_table_unprepared')
