"""Test-only bridge to real isolated SQL sessions; no live/TLS transport claim."""
from psycopg import sql
from appointment_system.storage import Store

class IsolatedStore(Store):
    _expected_host='localhost'
    def __init__(self,target,role):
        target.check_owned();self.target=target;self.role=role

    def _call(self,statement,parameters=(),**kwargs):
        parts=statement.split('%s')
        if len(parts)!=len(parameters)+1 or not statement.startswith('SELECT '):
            raise AssertionError('Only declared single-value entry calls are allowed in this test bridge.')
        query=parts[0]
        for value,part in zip(parameters,parts[1:]):query+=sql.Literal(value).as_string()+part
        result='SELECT to_jsonb(q.value) FROM ('+query.rstrip(';')+') q(value);'
        guards=[]
        from appointment_system.worker_authority import current
        turn=current()
        claim=kwargs.get('job_authority')
        if claim is not None:
            from appointment_system.job_authority import JobClaim
            if not isinstance(claim,JobClaim):raise AssertionError('Invalid isolated job authority')
            bound='SELECT appointment_system.require_job_claim('+','.join(sql.Literal(value).as_string() for value in claim.parameters())+');'
            guards.append(bound)
        authority=kwargs.get('resource_authority')
        if authority is not None:
            if self.role!='abs_company' or type(authority) is not tuple or len(authority)!=4:
                raise AssertionError('Invalid isolated resource authority')
            check='appointment_system.authorize_resource_operation('+','.join(sql.Literal(value).as_string() for value in authority)+')'
            bound="DO $guard$ BEGIN IF "+check+" IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'company session rejected'; END IF; END $guard$;"
            # The authority check and operation share exactly one transaction.
            guards.append(bound)
        if turn is not None and self.role=='abs_worker':
            bound='SELECT appointment_system.require_worker_turn('+','.join(sql.Literal(value).as_string() for value in turn.parameters())+');'
            guards.insert(0,bound)
        if guards:result='BEGIN;'+''.join(guards)+result+'COMMIT;'
        return self.target.value(result,role=self.role)
