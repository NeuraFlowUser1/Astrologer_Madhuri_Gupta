"""The two inspected recovery policies, applied only to independently proven copies."""
from dataclasses import dataclass
from datetime import timedelta
from .protocol import BackupError

@dataclass(frozen=True)
class Policy:
    mode:str
    recent_copies:int=0
    daily_days:int=0
    monthly_months:int=0

    def __post_init__(self):
        values=(self.recent_copies,self.daily_days,self.monthly_months)
        if any(type(value) is not int for value in values):raise BackupError('backup_retention_policy_invalid')
        if self.mode=='recent':
            valid=2<=self.recent_copies<=400 and self.daily_days==self.monthly_months==0
        elif self.mode=='calendar':
            valid=self.recent_copies==2 and 1<=self.daily_days<=366 and 1<=self.monthly_months<=24
        else:valid=False
        if not valid:raise BackupError('backup_retention_policy_invalid')

    @classmethod
    def parse(cls,value):
        if type(value) is not dict or set(value)!={'mode','recent_copies','daily_days','monthly_months'}:
            raise BackupError('backup_retention_policy_invalid')
        return cls(**value)

    def remove(self,copies,current,today):
        """Input is newest-first verified inventory, never raw Drive metadata."""
        if type(copies) is not list or not copies:raise BackupError('backup_current_not_verified')
        keys=[(item[1],item[2]) for item in copies]
        if len(keys)!=len(set(keys)):raise BackupError('backup_drive_run_ambiguous')
        if current not in keys:raise BackupError('backup_current_not_verified')
        if any(item[0].date()>today for item in copies):raise BackupError('backup_retention_future_archive')
        # An old manually resumed proof cannot prune today's recovery coverage.
        if current not in keys[:self.recent_copies]:return None
        keep=set(keys[:self.recent_copies])
        if self.mode=='calendar':
            first=today-timedelta(days=self.daily_days-1);month=today.year*12+today.month;seen=set()
            for day,run,attempt,_ in copies:
                key=(run,attempt);calendar_month=day.year*12+day.month
                if day.date()>=first:keep.add(key)
                if month-self.monthly_months+1<=calendar_month<=month and calendar_month not in seen:
                    keep.add(key);seen.add(calendar_month)
        # Bound each run; next run checks a fresh inventory after interruption.
        return [item for item in reversed(copies) if (item[1],item[2]) not in keep][:20]
