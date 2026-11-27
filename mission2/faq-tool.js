// clinic_faq tool. The agent calls this for any question about the clinic.
// Only facts listed here may be told to callers. Anything else: staff call back.
return [
  'Opening hours: Monday to Friday 9 a.m. to 5 p.m., last appointment starts at 4 p.m. Saturday 9 a.m. to 1 p.m., last appointment starts at 12 noon. Closed on Sunday.',
  'Therapists: Amina, Daniel and Sara.',
  'Appointments last 45 minutes and start on the hour.',
  'Bookings can be made from tomorrow up to 30 days ahead, by phone or with this assistant.',
  'Please bring comfortable clothes you can move in, and any scans or referral letters.',
  'Please give at least 24 hours notice to cancel or move an appointment.',
  'Prices, insurance and anything not listed here: a member of staff will call the caller back.',
].join('\n');
