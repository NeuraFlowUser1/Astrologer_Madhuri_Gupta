"""Approved bounded retention. Unknown or unverified files are never removed."""
from datetime import date,timedelta
from envelope import BackupError

PROJECT='004-sarsa-jyotish-sansthan'
OWNER='sarsajyotish@gmail.com'


def checked_record(record,folder):
    """Validate an exact owned archive; return its UTC date and verification flag."""
    try:
        props=record['appProperties'];day=date.fromisoformat(props['backupDay'])
        if (props.get('sarsaProject')!=PROJECT or props.get('format')!='aes256gcm-v1'
                or record.get('parents')!=[folder] or record.get('trashed') is True
                or [o.get('emailAddress','').lower() for o in record.get('owners',[])]!=[OWNER]
                or record.get('mimeType')!='application/octet-stream'):
            raise ValueError()
        kind=props.get('backupKind','daily');revision=props.get('sourceCommit','')
        if kind=='daily':name=f'sarsa-004-{day.isoformat()}.pgdump.aesgcm'
        elif kind=='checkpoint' and len(revision)==40 and all(c in '0123456789abcdef' for c in revision):
            name=f'sarsa-004-{day.isoformat()}-checkpoint-{revision}.pgdump.aesgcm'
        else:raise ValueError()
        if record.get('name')!=name or not 0<int(record['size'])<514*1024*1024:
            raise ValueError()
        verified=props.get('restoreVerified')=='1' and int(props.get('restoredMigrations','0'))>0
        return day,verified
    except (KeyError,TypeError,ValueError):raise BackupError('retention_archive_identity_invalid') from None


def candidates(records,folder,today,current_id):
    """Keep 30 UTC days, 12 calendar-month representatives and two newest copies."""
    ids=[r.get('id') for r in records]
    if len(ids)!=len(set(ids)) or current_id not in ids:
        raise BackupError('retention_inventory_ambiguous')
    checked=[]
    for record in records:
        day,verified=checked_record(record,folder)
        if day>today:raise BackupError('retention_future_archive')
        if verified:checked.append((day,record))
    checked.sort(key=lambda pair:(pair[0],pair[1].get('createdTime',''),pair[1]['id']),reverse=True)
    if current_id not in {record['id'] for _,record in checked}:
        raise BackupError('retention_current_not_verified')
    keep={current_id}|{record['id'] for _,record in checked[:2]}
    current_month=today.year*12+today.month
    months=set()
    for day,record in checked:
        if day>=today-timedelta(days=29):keep.add(record['id'])
        month=day.year*12+day.month
        if current_month-11<=month<=current_month and month not in months:
            keep.add(record['id']);months.add(month)
    # Oldest first, bounded; a following run safely recomputes actual inventory.
    return [record for _,record in reversed(checked) if record['id'] not in keep][:20]
