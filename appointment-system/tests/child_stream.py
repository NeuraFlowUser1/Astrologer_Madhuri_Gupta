"""Bounded test-only child messages; do not mix buffered text reads with readiness."""
import os
import selectors
import time

class ChildLines:
    def __init__(self,stream,limit=16384):
        self.fd=stream.fileno();self.limit=limit;self.buffer=b'';self.eof=False
        self.selector=selectors.DefaultSelector();self.selector.register(self.fd,selectors.EVENT_READ)

    def readline(self,timeout=1):
        deadline=time.monotonic()+timeout
        while True:
            end=self.buffer.find(b'\n')
            if end>=0:
                if end+1>=self.limit:raise ValueError('Child message exceeds the test boundary')
                line,self.buffer=self.buffer[:end+1],self.buffer[end+1:]
                return line.decode('utf-8')
            if len(self.buffer)>=self.limit:raise ValueError('Child message exceeds the test boundary')
            if self.eof:
                if self.buffer:raise ValueError('Incomplete child message')
                return ''
            remaining=max(0,deadline-time.monotonic())
            if not self.selector.select(timeout=remaining):return None
            data=os.read(self.fd,8192)
            if data:self.buffer+=data
            else:self.eof=True

    def close(self):self.selector.close()
