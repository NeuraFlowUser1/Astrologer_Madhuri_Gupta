import {test} from 'node:test';
import assert from 'node:assert/strict';
import {localDate,money,appointmentLabel,timeLabel,dateRange} from '../browser/display-formatting.mjs';

test('display dates follow the configured practice across the UTC day boundary',()=>{
 const instant='2026-10-03T22:30:00Z';
 assert.equal(localDate(instant,'Asia/Kolkata'),'2026-10-04');
 assert.equal(localDate(instant,'America/New_York'),'2026-10-03');
 assert.match(timeLabel(instant,'Asia/Kolkata'),/4:00\s*am/i);
 assert.match(appointmentLabel(instant,'Asia/Kolkata'),/4 Oct 2026/);
});

test('the selectable date window uses the server date through month and year changes',()=>{
 assert.deepEqual(dateRange({server_now:'2026-12-31T22:00:00Z',policy:{timezone:'Asia/Kolkata',horizon_days:10}}),
  {first_date:'2027-01-01',last_date:'2027-01-11',timezone:'Asia/Kolkata'});
 assert.deepEqual(dateRange({server_now:'2028-02-28T12:00:00Z',policy:{timezone:'UTC',horizon_days:2}}),
  {first_date:'2028-02-28',last_date:'2028-03-01',timezone:'UTC'});
});

test('displayed fees retain paise and Indian digit grouping',()=>{
 assert.equal(money(100),'₹1');
 assert.equal(money(101),'₹1.01');
 assert.equal(money(12345600),'₹1,23,456');
});

test('invalid dates and timezones are rejected instead of showing a different appointment',()=>{
 assert.throws(()=>localDate('invalid'),RangeError);
 assert.throws(()=>timeLabel('2026-10-03T12:00:00Z','unknown'),RangeError);
 assert.throws(()=>dateRange({server_now:'invalid',policy:{timezone:'UTC',horizon_days:10}}),RangeError);
});
