// Decide whether a booking can go ahead. Runs once for all items.
// Input items: booking rows for the requested date (may be a single empty item).
// Output: { book, httpStatus, row?, reply }. The insert only runs when book is true.
const CLINIC = {
  tz: 'Africa/Addis_Ababa',
  therapists: ['Amina', 'Daniel', 'Sara'],
  hours: { 1: [9, 16], 2: [9, 16], 3: [9, 16], 4: [9, 16], 5: [9, 16], 6: [9, 12] },
  maxDaysAhead: 30,
};
const no = (httpStatus, reply) => [{ json: { book: false, httpStatus, reply } }];

const body = $('Book appointment').first().json.body || {};
const date = String(body.date || '').trim();
let time = String(body.time || '').trim();
const wanted = String(body.therapist || '').trim();
const patientName = String(body.patientName || '').trim().slice(0, 80);
const phone = String(body.phone || '').replace(/[\s()-]/g, '');

const missing = [['date', date], ['time', time], ['patientName', patientName], ['phone', phone]].filter(([, v]) => !v).map(([k]) => k);
if (missing.length) return no(400, { booked: false, error: `Missing: ${missing.join(', ')}.` });
if (!/^\+?\d{7,15}$/.test(phone)) return no(400, { booked: false, error: `"${body.phone}" doesn't look like a phone number.` });
const tm = time.match(/^(\d{1,2}):(\d{2})$/);
if (!tm) return no(400, { booked: false, error: `"${time}" is not a time. Use HH:MM, 24-hour.` });
time = `${tm[1].padStart(2, '0')}:${tm[2]}`;

const day = DateTime.fromISO(date, { zone: CLINIC.tz });
if (!day.isValid || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return no(400, { booked: false, error: `"${date}" is not a date. Use YYYY-MM-DD.` });

const today = DateTime.now().setZone(CLINIC.tz).startOf('day');
const daysAhead = Math.round(day.startOf('day').diff(today, 'days').days);
const weekday = day.toFormat('cccc');
const range = CLINIC.hours[day.weekday];

let therapists = CLINIC.therapists;
if (wanted) {
  const match = CLINIC.therapists.find(t => t.toLowerCase() === wanted.toLowerCase());
  if (!match) return no(200, { booked: false, alternatives: [], message: `We have no therapist called ${wanted}. Our therapists are ${CLINIC.therapists.join(', ')}.` });
  therapists = [match];
}

const booked = $input.all().map(i => i.json).filter(r => r.date === date && r.status === 'booked');
const freeAt = (t, who) => who.filter(th => !booked.some(r => r.time === t && r.therapist === th));
const slots = range ? Array.from({ length: range[1] - range[0] + 1 }, (_, i) => `${String(range[0] + i).padStart(2, '0')}:00`) : [];

// Up to three nearby options: same time with another therapist first, then other times.
const alternatives = () => {
  const alts = [];
  if (wanted) freeAt(time, CLINIC.therapists).forEach(th => alts.push({ date, time, therapist: th }));
  const order = slots.slice().sort((a, b) => Math.abs(parseInt(a) - parseInt(time)) - Math.abs(parseInt(b) - parseInt(time)));
  for (const t of order) { if (t !== time) { const f = freeAt(t, therapists); if (f.length) alts.push({ date, time: t, therapist: f[0] }); } }
  return alts.slice(0, 3);
};

if (daysAhead < 1) return no(200, { booked: false, alternatives: [], message: 'We can only book from tomorrow onwards.' });
if (daysAhead > CLINIC.maxDaysAhead) return no(200, { booked: false, alternatives: [], message: `We only book up to ${CLINIC.maxDaysAhead} days ahead.` });
if (!range) return no(200, { booked: false, alternatives: [], message: `The clinic is closed on ${weekday}s.` });
if (!slots.includes(time)) return no(200, { booked: false, alternatives: alternatives(), message: `Appointments on ${weekday}s start on the hour between ${slots[0]} and ${slots[slots.length - 1]}.` });

// One caller can't be in two appointments at once.
const clash = booked.find(r => r.time === time && String(r.phone || '').replace(/[\s()-]/g, '') === phone);
if (clash) return no(200, { booked: false, alternatives: [], message: `This phone number already has an appointment at ${time} on ${weekday} ${date} with ${clash.therapist}, reference ${clash.bookingId}.` });

const free = freeAt(time, therapists);
if (!free.length) {
  const who = wanted ? therapists[0] : 'any therapist';
  return no(200, { booked: false, alternatives: alternatives(), message: `${time} on ${weekday} ${date} is already taken for ${who}.` });
}

const therapist = free[0];
const bookingId = `NG-${date.replace(/-/g, '').slice(2)}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
return [{ json: {
  book: true,
  httpStatus: 200,
  row: { bookingId, date, time, therapist, patientName, phone, status: 'booked', source: String(body.source || 'voice-agent').slice(0, 40) },
  reply: { booked: true, bookingId, date, weekday, time, therapist, message: `Booked with ${therapist} on ${weekday} ${date} at ${time}. Reference ${bookingId}.` },
} }];
