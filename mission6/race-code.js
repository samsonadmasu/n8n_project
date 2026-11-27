// Runs right after our booking row is saved, on a fresh read of every booking that day.
// Two callers can pass the "is it free?" check at the same moment and both save a row.
// Rule: the row saved first (lowest id) keeps the slot; every later one undoes itself.
const CLINIC = {
  tz: 'Africa/Addis_Ababa',
  therapists: ['Amina', 'Daniel', 'Sara'],
  hours: { 1: [9, 16], 2: [9, 16], 3: [9, 16], 4: [9, 16], 5: [9, 16], 6: [9, 12] },
};
const mine = $('Decide booking').first().json.row;
const all = $input.all().map(i => i.json).filter(r => r.date === mine.date && r.status === 'booked');
const sameSlot = all.filter(r => r.time === mine.time && r.therapist === mine.therapist).sort((a, b) => a.id - b.id);
const me = sameSlot.find(r => r.bookingId === mine.bookingId);

if (!me || sameSlot[0].bookingId === mine.bookingId) return [{ json: { won: true } }];

// We lost. Offer what is still free, ignoring our own row (it is about to be undone).
const taken = all.filter(r => r.bookingId !== mine.bookingId);
const isFree = (time, th) => !taken.some(r => r.time === time && r.therapist === th);
const day = DateTime.fromISO(mine.date, { zone: CLINIC.tz });
const [first, last] = CLINIC.hours[day.weekday] || [9, 16];
const hour = parseInt(mine.time, 10);
const alternatives = [];
CLINIC.therapists.filter(th => th !== mine.therapist && isFree(mine.time, th))
  .forEach(th => alternatives.push({ date: mine.date, time: mine.time, therapist: th }));
for (const d of [1, -1, 2, -2, 3, -3]) {
  const h = hour + d;
  const t = `${String(h).padStart(2, '0')}:00`;
  if (h >= first && h <= last && isFree(t, mine.therapist)) alternatives.push({ date: mine.date, time: t, therapist: mine.therapist });
}
return [{ json: {
  won: false,
  undoRowId: me.id,
  reply: { booked: false, alternatives: alternatives.slice(0, 3),
           message: `Sorry, ${mine.time} with ${mine.therapist} on ${day.toFormat('cccc')} ${mine.date} was just taken by another caller.` },
} }];
