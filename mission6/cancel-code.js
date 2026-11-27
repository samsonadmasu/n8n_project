// Decide which booking to cancel. Runs once for all items.
// Input items: booking rows for the requested date (may be a single empty item).
// A booking is only cancelled when the caller's phone matches it, so nobody can cancel someone else's.
// Output: { cancel, httpStatus, rowId?, reply }. The update only runs when cancel is true.
const no = (httpStatus, reply) => [{ json: { cancel: false, httpStatus, reply } }];
const normPhone = (p) => String(p || '').replace(/[\s()-]/g, '');

const body = $('Cancel appointment').first().json.body || {};
const phone = normPhone(body.phone);
const date = String(body.date || '').trim();
let time = String(body.time || '').trim();
const therapist = String(body.therapist || '').trim().toLowerCase();

const missing = [['phone', phone], ['date', date]].filter(([, v]) => !v).map(([k]) => k);
if (missing.length) return no(400, { cancelled: false, error: `Missing: ${missing.join(', ')}.` });
if (time) {
  const tm = time.match(/^(\d{1,2}):(\d{2})$/);
  if (!tm) return no(400, { cancelled: false, error: `"${time}" is not a time. Use HH:MM, 24-hour.` });
  time = `${tm[1].padStart(2, '0')}:${tm[2]}`;
}

const mine = $input.all().map(i => i.json)
  .filter(r => r.date === date && r.status === 'booked' && normPhone(r.phone) === phone && (!time || r.time === time)
    && (!therapist || String(r.therapist).toLowerCase() === therapist));

if (mine.length === 0) {
  return no(200, { cancelled: false, message: `I can't find a booking for that phone number on ${date}${time ? ' at ' + time : ''}.` });
}
if (mine.length > 1) {
  const times = mine.map(r => `${r.time} with ${r.therapist}`).join(' and ');
  return no(200, { cancelled: false, message: `There are ${mine.length} bookings for that number on ${date}: ${times}. Which time should I cancel?` });
}

const b = mine[0];
return [{ json: {
  cancel: true,
  httpStatus: 200,
  rowId: b.id,
  reply: { cancelled: true, bookingId: b.bookingId, date: b.date, time: b.time, therapist: b.therapist,
           message: `Cancelled the ${b.time} appointment with ${b.therapist} on ${b.date}. Reference ${b.bookingId}.` },
} }];
