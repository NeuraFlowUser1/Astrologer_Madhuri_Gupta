"""Compare safe preview facts, never include source rows or supplied file text."""
from .source import ConversionError
from .handover import HASH


def compare(previous,current):
    identity=('phase','installation_id','environment','layout','release_digest','structure_digest')
    if type(previous) is not dict or any(previous.get(name)!=current[name] for name in identity):
        raise ConversionError('conversion_preview_identity_mismatch')
    names=set(current['source_counts'])
    counts=previous.get('source_counts');digests=previous.get('source_table_digests')
    if (type(counts) is not dict or type(digests) is not dict or set(counts)!=names or set(digests)!=names
            or any(type(counts[name]) is not int or counts[name]<0 or type(digests[name]) is not str
                   or not HASH.fullmatch(digests[name]) for name in names)):
        raise ConversionError('conversion_preview_invalid')
    changes=[{'table':name,'previous_count':counts[name],'current_count':current['source_counts'][name],
              'contents_changed':digests[name]!=current['source_table_digests'][name]}
             for name in sorted(names) if counts[name]!=current['source_counts'][name]
             or digests[name]!=current['source_table_digests'][name]]
    return {'source_changed':bool(changes),'source_changes':changes,
            'records_changed':False,'writers_fenced':False}
