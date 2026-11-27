// Work out free start times for one day. Runs once for all items.
// Input items: booking rows for the requested date (may be a single empty item).
const CLINIC = {
  tz: 'Africa/Addis_Ababa',
  therapists: ['Amina', 'Daniel', 'Sara'],
  // ISO weekday (1 = Monday) -> [first start hour, last start hour]. Sunday missing = closed.
  hours: { 1: [9, 16], 2: [9, 16], 3: [9, 16], 4: [9, 16], 5: [9, 16], 6: [9, 12] },
  maxDaysAhead: 30,
};
const out = (httpStatus, reply) => [{ json: { httpStatus, reply } }];

const body = $('Check availability').first().json.body || {};
const date = String(body.date || '').trim();
const wanted = String(body.therapist || '').trim();
if (!date) return out(400, { error: 'date is required, as YYYY-MM-DD.' });

const day = DateTime.fromISO(date, { zone: CLINIC.tz });
if (!day.isValid || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return out(400, { error: `"${date}" is not a date. Use YYYY-MM-DD.` });

const today = DateTime.now().setZone(CLINIC.tz).startOf('day');
const daysAhead = Math.round(day.startOf('day').diff(today, 'days').days);
const weekday = day.toFormat('cccc');
const closed = (message) => out(200, { date, weekday, open: false, free: [], message });

if (daysAhead < 1) return closed('We can only book from tomorrow onwards.');
if (daysAhead > CLINIC.maxDaysAhead) return closed(`We only book up to ${CLINIC.maxDaysAhead} days ahead.`);
const range = CLINIC.hours[day.weekday];
if (!range) return closed(`The clinic is closed on ${weekday}s.`);

let therapists = CLINIC.therapists;
if (wanted) {
  const match = CLINIC.therapists.find(t => t.toLowerCase() === wanted.toLowerCase());
  if (!match) return out(200, { date, weekday, open: true, free: [], message: `We have no therapist called ${wanted}. Our therapists are ${CLINIC.therapists.join(', ')}.` });
  therapists = [match];
}

const booked = $input.all().map(i => i.json).filter(r => r.date === date && r.status === 'booked');
const free = [];
for (let h = range[0]; h <= range[1]; h++) {
  const time = `${String(h).padStart(2, '0')}:00`;
  const taken = booked.filter(r => r.time === time).map(r => r.therapist);
  const available = therapists.filter(t => !taken.includes(t));
  if (available.length) free.push({ time, therapists: available });
}

return out(200, {
  date, weekday, open: true, therapist: wanted ? therapists[0] : null, free,
  message: free.length ? `${free.length} start times free on ${weekday} ${date}. Appointments last 45 minutes.` : `Fully booked on ${weekday} ${date}.`,
});
