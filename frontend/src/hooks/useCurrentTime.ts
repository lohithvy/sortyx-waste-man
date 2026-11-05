import { useState, useEffect } from 'react';

interface CurrentTime {
  time: string; // e.g. "10:24 AM"
  date: string; // e.g. "Tue, Nov 4, 2026"
}

export function useCurrentTime(): CurrentTime {
  const format = (): CurrentTime => {
    const now = new Date();

    // Format in IST (Asia/Kolkata)
    const timeStr = now.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Asia/Kolkata',
    });

    const dateStr = now.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    });

    return { time: timeStr, date: dateStr };
  };

  const [current, setCurrent] = useState<CurrentTime>(format);

  useEffect(() => {
    const id = setInterval(() => setCurrent(format()), 1000);
    return () => clearInterval(id);
  }, []);

  return current;
}
