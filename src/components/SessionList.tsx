import React, { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

type Session = {
  id: string;
  event_id: string;
  location_id: string;
};

export default function SessionList() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const { data, error } = await supabase.from('sessions').select('*');
        if (error) throw error;
        setSessions(data || []);
      } catch (err: any) {
        setError(err.message || 'Unbekannter Fehler');
      } finally {
        setLoading(false);
      }
    };

    fetchSessions();
  }, []);

  if (loading) return <div className="login-container">🔄 Lade Aufgüsse...</div>;
  if (error) return <div className="login-container">❌ Fehler: {error}</div>;

  if (sessions.length === 0) {
    return <div className="login-container">ℹ️ Keine Aufgüsse gefunden.</div>;
  }

  return (
    <div className="session-list">
      <h2>🧖‍♂️ Geplante Aufgüsse</h2>
      <ul>
        {sessions.map((session) => (
          <li key={session.id}>
            📅 Event-ID: {session.event_id} &nbsp;|&nbsp; 📍 Ort-ID: {session.location_id}
          </li>
        ))}
      </ul>
    </div>
  );
}
