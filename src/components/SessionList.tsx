import { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

type Session = {
  id: string;
  event_id: string;
  location_id: string;
};

export default function SessionList() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSessions = async () => {
      const { data, error } = await supabase.from('sessions').select('*');

      if (error) {
        setError(error.message);
      } else {
        setSessions(data || []);
      }
      setLoading(false);
    };

    loadSessions();
  }, []);

  if (loading) return <div className="login-container">Lade Aufgüsse...</div>;
  if (error) return <div className="login-container">Fehler: {error}</div>;

  return (
    <div className="session-list">
      <h2>Geplante Aufgüsse</h2>
      <ul>
        {sessions.map((session) => (
          <li key={session.id}>
            📅 Event: {session.event_id} — 📍 Ort: {session.location_id}
          </li>
        ))}
      </ul>
    </div>
  );
}
