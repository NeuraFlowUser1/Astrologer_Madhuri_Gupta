"""Recognize an exact reviewed historical layout before reading private rows.

Ledger hashes alone cannot detect altered tables, constraints, functions,
indexes or trigger behaviour. The digest binds these without private data.
The serving engine never chooses business logic by a historical project name.
"""
from dataclasses import dataclass,replace
from copy import deepcopy
from pathlib import Path
import hashlib,json,re
from psycopg import sql

SCHEMAS=('public','booking_control','sarsa_booking')
EXCLUDED=('schema_migrations',)
CATALOG=Path(__file__).with_name('source-layouts.json')

class ConversionError(ValueError):
    """Stable non-private error code; SQL/provider values never become messages."""

def canonical(value):
    # Offline schema metadata can be larger than an ordinary HTTP document.
    # This never changes the serving boundary's independent 128 KiB maximum.
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    except (TypeError,ValueError,RecursionError):raise ConversionError('conversion_document_invalid') from None

def _pairs(items):
    value={}
    for key,item in items:
        if key in value:raise ConversionError('conversion_duplicate_field')
        value[key]=item
    return value

@dataclass(frozen=True)
class Layout:
    identifier:str
    project:str
    major:int
    schema:str
    ledger:dict
    structure:dict
    variants:tuple=()

    @property
    def digest(self):return hashlib.sha256(canonical(self.structure)).hexdigest()

def structure(connection):
    # PostgreSQL deparses visible public foreign keys without a schema prefix.
    # Fix the inspection context rather than accept several loose fingerprints.
    previous=connection.execute("SELECT current_setting('search_path')").fetchone()[0]
    connection.execute("SELECT set_config('search_path','pg_catalog,public',false)")
    try:return _structure(connection)
    finally:
        connection.execute("SELECT set_config('search_path',%s,false)",(previous,))

def _structure(connection):
    relation_rows=connection.execute("""SELECT n.nspname,c.relname,a.attname,
        pg_catalog.format_type(a.atttypid,a.atttypmod),NOT a.attnotnull,
        pg_get_expr(d.adbin,d.adrelid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p') AND NOT c.relname=ANY(%s)
        ORDER BY n.nspname,c.relname,a.attnum""",(list(SCHEMAS),list(EXCLUDED))).fetchall()
    relations={}
    for schema,table,name,kind,nullable,default in relation_rows:
        relations.setdefault(schema+'.'+table,[]).append(dict(name=name,type=kind,nullable=nullable,default=default))
    constraints=[list(row) for row in connection.execute("""SELECT n.nspname,c.relname,k.conname,k.contype,
        pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s)
        AND NOT c.relname=ANY(%s) ORDER BY n.nspname,c.relname,k.conname""",
        (list(SCHEMAS),list(EXCLUDED))).fetchall()]
    indexes=[list(row) for row in connection.execute("""SELECT n.nspname,c.relname AS table_name,i.relname AS index_name,pg_get_indexdef(i.oid)
        FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s)
        AND NOT c.relname=ANY(%s) ORDER BY n.nspname,c.relname,i.relname""",
        (list(SCHEMAS),list(EXCLUDED))).fetchall()]
    functions=[]
    for schema,name,args,definition in connection.execute("""SELECT n.nspname,p.proname,
        pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=ANY(%s) AND p.prokind='f'
        AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
          AND d.objid=p.oid AND d.deptype='e') ORDER BY n.nspname,p.proname,3""",(list(SCHEMAS),)).fetchall():
        functions.append([schema,name,args,hashlib.sha256(definition.encode()).hexdigest()])
    triggers=[list(row) for row in connection.execute("""SELECT n.nspname,c.relname,t.tgname,t.tgenabled,
        pg_get_triggerdef(t.oid) AS definition
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=ANY(%s) AND NOT t.tgisinternal
        AND NOT c.relname=ANY(%s)
        ORDER BY n.nspname,c.relname,t.tgname""",(list(SCHEMAS),list(EXCLUDED))).fetchall()]
    return dict(relations=relations,constraints=constraints,indexes=indexes,functions=functions,triggers=triggers)

def catalogue():
    if CATALOG.is_symlink() or not CATALOG.is_file() or CATALOG.stat().st_size>1048576:
        raise ConversionError('conversion_catalogue_missing')
    try:value=json.loads(CATALOG.read_text(),object_pairs_hook=_pairs)
    except (ValueError,UnicodeError,RecursionError):raise ConversionError('conversion_catalogue_invalid') from None
    if (type(value) is not dict or set(value)!={'version','layouts'} or type(value['version']) is not int
        or value['version']!=1 or type(value['layouts']) is not list or not 1<=len(value['layouts'])<=20):
        raise ConversionError('conversion_catalogue_invalid')
    result=[]
    for item in value['layouts']:
        if (type(item) is not dict or set(item)-{'function_variants'}!={'identifier','project','major','schema','ledger','structure','structure_digest'}
            or item['project'] not in ('003','004') or type(item['major']) is not int or item['major'] not in (16,18)
            or item['schema']!=('public' if item['project']=='003' else 'sarsa_booking')
            or type(item['identifier']) is not str or not re.fullmatch('legacy-'+item['project']+'-[1-9][0-9]{0,3}',item['identifier'])
            or type(item['ledger']) is not dict or not item['ledger']
            or any(type(name) is not str or not re.fullmatch('[0-9]{3}_[a-z0-9_]+\\.sql',name)
              or type(digest) is not str or not re.fullmatch('[a-f0-9]{64}',digest) for name,digest in item['ledger'].items())
            or type(item['structure']) is not dict or set(item['structure'])!={'relations','constraints','indexes','functions','triggers'}):
            raise ConversionError('conversion_catalogue_invalid')
        layout=Layout(**{key:value for key,value in item.items() if key not in ('structure_digest','function_variants')})
        if layout.digest!=item['structure_digest']:raise ConversionError('conversion_catalogue_invalid')
        variants=item.get('function_variants',[])
        if type(variants) is not list or len(variants)>4:raise ConversionError('conversion_catalogue_invalid')
        alternatives=[]
        for variant in variants:
            if (type(variant) is not dict or set(variant)!={'structure_digest','replacements'}
                    or type(variant['replacements']) is not list or not 1<=len(variant['replacements'])<=100):
                raise ConversionError('conversion_catalogue_invalid')
            changed=deepcopy(layout.structure);seen=set()
            for replacement in variant['replacements']:
                if (type(replacement) is not list or len(replacement)!=5
                        or any(type(value) is not str for value in replacement)
                        or any(not re.fullmatch('[a-f0-9]{64}',value) for value in replacement[3:])):
                    raise ConversionError('conversion_catalogue_invalid')
                original=replacement[:4];identity=tuple(replacement[:3])
                if original not in changed['functions'] or identity in seen or replacement[3]==replacement[4]:
                    raise ConversionError('conversion_catalogue_invalid')
                seen.add(identity);changed['functions'][changed['functions'].index(original)]=replacement[:3]+replacement[4:]
            alternative=replace(layout,structure=changed)
            if alternative.digest!=variant['structure_digest'] or alternative.digest in {value.digest for value in alternatives}:
                raise ConversionError('conversion_catalogue_invalid')
            alternatives.append(alternative)
        layout=replace(layout,variants=tuple(alternatives))
        result.append(layout)
    if not result or len({item.identifier for item in result})!=len(result):
        raise ConversionError('conversion_catalogue_invalid')
    return tuple(result)

def detect(connection):
    major=int(connection.execute("SELECT current_setting('server_version_num')").fetchone()[0])//10000
    current=structure(connection);digest=hashlib.sha256(canonical(current)).hexdigest()
    choices=[candidate for item in catalogue() for candidate in (item,*item.variants)
             if candidate.major==major and candidate.digest==digest]
    if len(choices)!=1:raise ConversionError('legacy_structure_unrecognized')
    selected=choices[0]
    table=sql.Identifier(selected.schema,'schema_migrations')
    if connection.execute('SELECT to_regclass(%s)',(selected.schema+'.schema_migrations',)).fetchone()[0] is None:
        raise ConversionError('legacy_migration_ledger_missing')
    fields=('name','checksum') if selected.project=='003' else ('version','sha256')
    ledger=dict(connection.execute(sql.SQL('SELECT {},{} FROM {}').format(
        sql.Identifier(fields[0]),sql.Identifier(fields[1]),table)).fetchall())
    if ledger!=selected.ledger:raise ConversionError('legacy_migration_ledger_changed')
    return selected

def read_rows(connection,layout):
    """Must be called in one read-consistent transaction; never writes an export.

    A private caller can inspect/migrate these in memory. CLI output contains
    counts/digests only. No row is skipped because it looks old or inconvenient.
    """
    rows={}
    for qualified in layout.structure['relations']:
        schema,table=qualified.split('.')
        records=connection.execute(sql.SQL("WITH utc AS MATERIALIZED (SELECT set_config('TimeZone','UTC',true)) "+
            'SELECT to_jsonb(t) FROM utc CROSS JOIN {} t').format(sql.Identifier(schema,table))).fetchall()
        rows[qualified]=[item[0] for item in records]
    return rows

def row_fingerprints(rows):
    """Order-independent private-content evidence, without saved plaintext."""
    return {table:hashlib.sha256(canonical(sorted(canonical(row).decode() for row in records))).hexdigest()
            for table,records in rows.items()}
