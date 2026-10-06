"""Fixed maintenance operations; no raw table read/write or production-owner login."""
from psycopg.types.json import Jsonb
from .control_recovery import RecoveryDatabase

class PrivacyDatabase(RecoveryDatabase):
    def inspect(self,policy,*,limit=100,after=None):
        return self.call('SELECT appointment_system.control_privacy_candidates(%s,%s,%s,NULL)',(policy,limit,after))
    def record(self,operation,policy,target,target_hash,base_sequence):
        return self.call('SELECT appointment_system.control_privacy_record_intent(%s,%s,%s,%s,%s)',(operation,policy,target,target_hash,base_sequence))
    def saved_intent(self,operation):return self.call('SELECT appointment_system.privacy_saved_intent(%s)',(operation,))
    def freeze(self,operation,record):return self.call('SELECT appointment_system.privacy_freeze(%s,%s)',(operation,Jsonb(record)))
    def attach(self,operation,proof):
        return self.call('SELECT appointment_system.control_privacy_attach_export(%s,%s,%s,%s,%s)',(operation,proof['sequence'],proof['entry_hash'],proof['head_hash'],proof['file_id']))
    def required_sequence(self):return self.call('SELECT appointment_system.privacy_required_sequence()')
    def replay_apply(self,restore,operation):return self.call('SELECT appointment_system.control_privacy_replay_apply(%s,%s)',(restore,operation))
    def apply(self,operation):return self.call('SELECT appointment_system.control_privacy_apply(%s)',(operation,))
    def restore_intent(self,record,proof):
        return self.call('SELECT appointment_system.privacy_restore_intent(%s,%s,%s,%s,%s)',(Jsonb(record),proof['sequence'],proof['entry_hash'],proof['head_hash'],proof['file_id']))
    def finish_replay(self,operation,generation,sequence,head_hash):
        return self.call('SELECT appointment_system.privacy_finish_replay(%s,%s,%s,%s)',(operation,generation,sequence,head_hash))
