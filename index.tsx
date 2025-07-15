/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import SessionList from './components/SessionList';

declare global {
    interface Window {
        instgrm?: {
            Embeds: {
                process: () => void;
            };
        };
        tiktok?: {
            embed: {
                render: () => void;
            };
        };
    }
}

// --- MOCK DATA & TYPES ---

type Permission = 'delete_content' | 'create_festivals' | 'manage_users';

type User = {
    id: number;
    name: string;
    nickname?: string;
    email: string;
    phone?: string;
    primarySauna: string;
    avatarUrl: string;
    qualifications: string[];
    awards: string[];
    aufgussCount: number;
    workHours: number;
    isAdmin: boolean;
    permissions: Permission[];
    status: 'active'; // pending_approval is removed
    shortNoticeCancellations: number;
    username?: string;
    showInMemberList: boolean;
    lastProfileUpdate?: number;
    lastAufgussShareTimestamp?: number;
    motto?: string;
};

type Aufguss = {
    id: string;
    location: string;
    sauna: string;
    date: string;
    time: string;
    aufgussmeisterId: number | null;
    aufgussmeisterName: string | null;
    type: string | null;
};

type FestivalParticipant = {
    userId: number;
    status: 'attending' | 'not_attending' | 'pending';
    aufgussAvailability: string[];
    workHours: number;
    hoursLogged: boolean;
    aufgussProposals: { id: string; name: string }[];
};

type FestivalTask = {
    id: number;
    description: string;
    responsible: number | null; // User ID
};

type Festival = {
    id: string;
    name: string;
    startDate: string;
    endDate: string;
    rsvpDeadline: string;
    location: string;
    numberOfSaunas: number;
    aufgussTimes: string[];
    tasks: FestivalTask[];
    participants: FestivalParticipant[];
}

type Comment = {
    id: number;
    userId: number;
    text: string;
};

type PollData = {
    question: string;
    options: { text: string; votes: number[] }[]; // Store user IDs who voted
};

type Post = {
    id: number;
    userId: number;
    type: 'text' | 'poll' | 'image' | 'embed';
    content: string; // Used for text posts, poll question, image caption or embed caption
    pollData?: PollData;
    imageUrl?: string; // For image posts (base64)
    embedUrl?: string; // For embed posts
    timestamp: string;
    likes: number[];
    comments: Comment[];
};

type Award = {
    id: string;
    name: string;
    icon: string;
    color: string;
}

type View = 'login' | 'dashboard' | 'social' | 'aufguss' | 'festival' | 'mitglieder' | 'berichte' | 'profile' | 'register' | 'profile_setup';
type AppStage = 'loading' | 'login' | 'register' | 'profile_setup' | 'loggedIn';


const AVAILABLE_PERMISSIONS: { id: Permission, description: string }[] = [
    { id: 'delete_content', description: 'Beiträge & Kommentare löschen' },
    { id: 'create_festivals', description: 'Saunafeste erstellen & verwalten' },
    { id: 'manage_users', description: 'Rechte & Mitglieder verwalten' },
];

const SAUNA_LOCATIONS = ['Panoramabad Freudenstadt', 'Albthermen Bad Urach', 'Saunawelt Höchenschwand'];
const LOCATION_SAUNAS: Record<string, string[]> = {
    [SAUNA_LOCATIONS[0]]: ['80° Kelo Sauna', '100° Blockhaus Sauna'],
    [SAUNA_LOCATIONS[1]]: ['Mineraltherme-Sauna'],
    [SAUNA_LOCATIONS[2]]: ['Natur-Sauna', 'Schwarzwald-Hütte'],
};

const DEFAULT_AUFGUSS_TYPES = ['Räucherritual', 'Duftreise mit 3 ätherischen Ölen', 'Kräutersud', 'Haferpflaumen Schnapsaufguss'];
const DEFAULT_QUALIFICATIONS = ['Saunameister Basic', 'Saunameister Pro', 'Eventmanagement', 'Ersthelfer'];


const EMOJI_AVATARS = ['🔥', '😎', '👑', '🚀', '🌟', '🧘', '🧙', '🤖', '🦄', '💎', '💡', '🏆', '🎯', '💪', '🌊', '🌲', '🏔️', '🦉', '🦊', '🦅', '🦁', '🐉', '⚔️', '🛡️', '🔑'];

const FALLBACK_BACKGROUND_URLS: Record<View | string, string> = {
    login: "https://images.pexels.com/photos/7241416/pexels-photo-7241416.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    register: "https://images.pexels.com/photos/7241416/pexels-photo-7241416.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    profile_setup: "https://images.pexels.com/photos/1562/italian-landscape-mountains-nature.jpg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    pending: "https://images.pexels.com/photos/2310641/pexels-photo-2310641.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    dashboard: "https://images.pexels.com/photos/3768894/pexels-photo-3768894.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    social: "https://images.pexels.com/photos/1528660/pexels-photo-1528660.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    aufguss: "https://images.pexels.com/photos/13159187/pexels-photo-13159187.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    festival: "https://images.pexels.com/photos/1191275/pexels-photo-1191275.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    mitglieder: "https://images.pexels.com/photos/421927/pexels-photo-421927.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    berichte: "https://images.pexels.com/photos/9754/mountains-clouds-forest-fog.jpg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    profile: "https://images.pexels.com/photos/6104977/pexels-photo-6104977.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    // Holiday Fallbacks
    nikolaus: "https://images.pexels.com/photos/3224164/pexels-photo-3224164.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    christmas: "https://images.pexels.com/photos/3224164/pexels-photo-3224164.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    silvester: "https://images.pexels.com/photos/34098/night-shot-fireworks-new-year-s-eve-34098.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    easter: "https://images.pexels.com/photos/4054737/pexels-photo-4054737.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
};


const MOCK_AWARDS: Award[] = [
    { id: 'aufguss_bronze', name: 'Aufguss-Meister (Bronze)', icon: 'military_tech', color: '#CD7F32' },
    { id: 'aufguss_silver', name: 'Aufguss-Meister (Silber)', icon: 'military_tech', color: '#C0C0C0' },
    { id: 'aufguss_gold', name: 'Aufguss-Meister (Gold)', icon: 'military_tech', color: '#FFD700' },
    { id: 'fleissiger_helfer', name: 'Fleißiger Helfer', icon: 'construction', color: 'var(--success-color)' },
    { id: 'event_organisator', name: 'Event-Organisator', icon: 'celebration', color: 'var(--admin-color)' },
    { id: 'sauna_wanderer', name: 'Sauna-Wanderer', icon: 'hiking', color: '#8D6E63' },
    { id: 'kraeuter_hexe', name: 'Kräuter-Hexe', icon: 'spa', color: '#2E7D32' },
    { id: 'fels_in_der_brandung', name: 'Fels in der Brandung', icon: 'verified', color: '#1565C0' },
    { id: 'nachteule', name: 'Nachteule', icon: 'dark_mode', color: '#4527A0' },
    { id: 'fruehaufsteher', name: 'Frühaufsteher', icon: 'light_mode', color: '#FB8C00' },
    { id: 'social_butterfly', name: 'Social Butterfly', icon: 'groups', color: '#D81B60' },
    { id: 'zeremonienmeister', name: 'Zeremonienmeister', icon: 'auto_stories', color: '#6A1B9A' },
    { id: 'hitze_titan', name: 'Hitze-Titan', icon: 'local_fire_department', color: '#BF360C' },
    { id: 'planungs_genie', name: 'Planungs-Genie', icon: 'event_available', color: '#00695C' },
    { id: 'vereins_legende', name: 'Vereins-Legende', icon: 'workspace_premium', color: '#B71C1C' },
];

const MOCK_USERS: User[] = [
    { id: 1, name: 'Christoph René Wolfert', nickname: 'Der Aufgiesser', email: 'chris@example.com', primarySauna: 'Panoramabad Freudenstadt', avatarUrl: `https://i.pravatar.cc/150?u=1`, qualifications: ['Saunameister Pro', 'Eventmanagement'], awards: ['aufguss_gold', 'event_organisator', 'vereins_legende'], aufgussCount: 99, workHours: 150, isAdmin: true, permissions: ['delete_content', 'create_festivals', 'manage_users'], status: 'active', shortNoticeCancellations: 0, username: 'admin', showInMemberList: true, lastProfileUpdate: 0, lastAufgussShareTimestamp: 0, motto: "Der Wald ruft." },
    { id: 2, name: 'Max Mustermann', email: 'max@example.com', primarySauna: 'Saunawelt Höchenschwand', avatarUrl: `🔥`, qualifications: ['Saunameister Basic'], awards: ['aufguss_bronze', 'hitze_titan'], aufgussCount: 12, workHours: 25, isAdmin: false, permissions: [], status: 'active', shortNoticeCancellations: 1, username: 'max', showInMemberList: true, lastProfileUpdate: 0, lastAufgussShareTimestamp: 0, motto: "Schwitzen für den Sieg." },
    { id: 3, name: 'Anna Schmidt', email: 'anna@example.com', primarySauna: 'Albthermen Bad Urach', avatarUrl: `https://i.pravatar.cc/150?u=3`, qualifications: [], awards: [], aufgussCount: 0, workHours: 0, isAdmin: false, permissions: [], status: 'active', shortNoticeCancellations: 0, username: 'anna', showInMemberList: true, lastProfileUpdate: 0, lastAufgussShareTimestamp: 0, motto: "" },
];

const MOCK_POSTS: Post[] = [
    {
        id: 1, userId: 2, type: 'text', content: 'Freue mich schon auf das Sommer-Saunafest! Wer ist alles dabei?',
        timestamp: 'Vor 2 Stunden', likes: [1],
        comments: [{ id: 1, userId: 1, text: 'Ich bin auf jeden Fall da und übernehme die Playlist!' }]
    },
    {
        id: 2, userId: 1, type: 'text', content: 'Der neue Kräutersud-Aufguss ist fertig vorbereitet. Ein echtes Erlebnis!',
        timestamp: 'Gestern', likes: [], comments: []
    },
     {
        id: 3,
        userId: 1,
        type: 'poll',
        content: 'Welcher neue Aufguss-Duft soll als nächstes ins Programm?',
        pollData: {
            question: 'Welcher neue Aufguss-Duft soll als nächstes ins Programm?',
            options: [
                { text: 'Zirbe-Latschenkiefer', votes: [2] },
                { text: 'Orange-Ingwer', votes: [] },
                { text: 'Sandelholz-Vanille', votes: [1] }
            ]
        },
        timestamp: 'Vor 3 Tagen',
        likes: [2],
        comments: []
    }
];

// --- HELPERS ---

const getThursdayBefore = (startDate: Date): Date => {
    const date = new Date(startDate);
    date.setHours(0,0,0,0);
    // Go back day by day until we hit Thursday (day 4)
    let daysToGoBack = (date.getDay() + 7 - 4) % 7;
    if (daysToGoBack === 0) daysToGoBack = 7; // If it's already Thursday, go to previous Thursday
    date.setDate(date.getDate() - daysToGoBack);
    date.setHours(22, 0, 0, 0);
    return date;
};

const upcomingFestivalDate = new Date();
upcomingFestivalDate.setDate(upcomingFestivalDate.getDate() + 10); // Start in 10 days
const upcomingFestivalEndDate = new Date(upcomingFestivalDate);
upcomingFestivalEndDate.setDate(upcomingFestivalDate.getDate() + 2); // Lasts 3 days

const MOCK_FESTIVALS: Festival[] = [
    {
        id: 'sommerfest-2024',
        name: 'Sommer-Saunafest 2024',
        startDate: upcomingFestivalDate.toISOString().split('T')[0],
        endDate: upcomingFestivalEndDate.toISOString().split('T')[0],
        rsvpDeadline: getThursdayBefore(upcomingFestivalDate).toISOString(),
        location: SAUNA_LOCATIONS[0],
        numberOfSaunas: 2,
        aufgussTimes: ['10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00'],
        tasks: [
            { id: 1, description: 'Getränke für die Saunanacht organisieren', responsible: null },
            { id: 2, description: 'Musik-Playlist erstellen', responsible: 1 }, // Assigned to admin
            { id: 3, description: 'Dekoration für den Ruhebereich besorgen', responsible: null },
            { id: 4, description: 'Holz für Feuerstelle hacken', responsible: 2 }, // Assigned to Max
        ],
        participants: MOCK_USERS.map(u => ({
            userId: u.id,
            status: u.id === 1 ? 'attending' : 'pending',
            aufgussAvailability: u.id === 1 ? ['10:00', '14:00', '18:00'] : [],
            workHours: 0,
            hoursLogged: false,
            aufgussProposals: u.id === 1 ? [{id: '1', name: 'Sommernachtstraum'}] : []
        }))
    }
];

const generateInitialAufguesse = (): Aufguss[] => {
    const aufguesse: Aufguss[] = [];
    const today = new Date();

    for (let day = 0; day < 30; day++) {
        const currentDate = new Date(today);
        currentDate.setDate(today.getDate() + day);
        const dateStr = currentDate.toISOString().split('T')[0];
        const dayOfWeek = currentDate.getDay(); // 0=Sunday, 1=Monday, ...

        // --- Panoramabad Freudenstadt ---
        const fdsSaunas = LOCATION_SAUNAS[SAUNA_LOCATIONS[0]];
        let fdsTimes: string[] = [];
        if (dayOfWeek >= 2 && dayOfWeek <= 4) { // Di, Mi, Do
            for (let hour = 14; hour <= 20; hour++) fdsTimes.push(`${hour}:00`);
        } else if (dayOfWeek >= 5 || dayOfWeek === 0) { // Fr, Sa, So
            for (let hour = 11; hour <= 20; hour++) fdsTimes.push(`${hour}:00`);
        }
        fdsSaunas.forEach(sauna => {
            fdsTimes.forEach(time => {
                aufguesse.push({
                    id: `${SAUNA_LOCATIONS[0]}-${sauna}-${dateStr}-${time}`,
                    location: SAUNA_LOCATIONS[0], sauna, date: dateStr, time,
                    aufgussmeisterId: null, aufgussmeisterName: null, type: null,
                });
            });
        });

        // --- Albthermen Bad Urach ---
        const urachSaunas = LOCATION_SAUNAS[SAUNA_LOCATIONS[1]];
        const urachTimes: string[] = [];
        for (let hour = 10; hour <= 20; hour++) urachTimes.push(`${hour}:30`);
        urachSaunas.forEach(sauna => {
            urachTimes.forEach(time => {
                aufguesse.push({
                    id: `${SAUNA_LOCATIONS[1]}-${sauna}-${dateStr}-${time}`,
                    location: SAUNA_LOCATIONS[1], sauna, date: dateStr, time,
                    aufgussmeisterId: null, aufgussmeisterName: null, type: null,
                });
            });
        });

        // --- Saunawelt Höchenschwand (closed until end of August) ---
        const hoechenschwandClosureDate = new Date(currentDate.getFullYear(), 7, 31); // August 31st
        if (currentDate > hoechenschwandClosureDate) {
            const hswSaunas = LOCATION_SAUNAS[SAUNA_LOCATIONS[2]];
            const hswTimes: string[] = [];
             for (let hour = 10; hour <= 20; hour++) hswTimes.push(`${hour}:00`);
             hswSaunas.forEach(sauna => {
                hswTimes.forEach(time => {
                    aufguesse.push({
                        id: `${SAUNA_LOCATIONS[2]}-${sauna}-${dateStr}-${time}`,
                        location: SAUNA_LOCATIONS[2], sauna, date: dateStr, time,
                        aufgussmeisterId: null, aufgussmeisterName: null, type: null,
                    });
                });
            });
        }
    }
    // Add a past aufguss for user 2 for testing the "days since" feature
     aufguesse.push({
        id: 'test-aufguss-past',
        location: SAUNA_LOCATIONS[0],
        sauna: LOCATION_SAUNAS[SAUNA_LOCATIONS[0]][0],
        date: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // 15 days ago
        time: '18:00',
        aufgussmeisterId: 2,
        aufgussmeisterName: 'Max Mustermann',
        type: 'Test Aufguss'
    });
    return aufguesse;
};

// --- HELPERS ---

const safeJSONParse = (key: string, fallback: any) => {
    try {
        const saved = localStorage.getItem(key);
        // Ensure saved is not null, undefined, or an empty string before parsing
        if (saved) {
            return JSON.parse(saved);
        }
        return fallback;
    } catch (e) {
        console.error(`Failed to parse ${key} from localStorage`, e);
        return fallback;
    }
};


const getHoliday = (today: Date): string | null => {
    const month = today.getMonth(); // 0-11
    const day = today.getDate();

    // Ostern (Easter) - Example for a year like 2024: March 29 - April 1
    // Note: This is a simplified check. A real-world app would need a proper algorithm for moveable feasts.
    if ((month === 2 && day >= 29) || (month === 3 && day <= 1)) return 'easter';

    // Nikolaus: Dec 5 - 7
    if (month === 11 && day >= 5 && day <= 7) return 'nikolaus';

    // Weihnachten (Christmas): Dec 20 - 27
    if (month === 11 && day >= 20 && day <= 27) return 'christmas';
    
    // Silvester (New Year's Eve): Dec 30 - Jan 2
    if (month === 11 && day >= 30) return 'silvester';
    if (month === 0 && day <= 2) return 'silvester';

    return null;
}

const calculateDaysSinceLastAufguss = (userId: number, allAufguesse: Aufguss[]): number | null => {
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Normalize today to the start of the day

    const userAufguesseInPast = allAufguesse
        .filter(a => a.aufgussmeisterId === userId && new Date(a.date) < today)
        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

    if (userAufguesseInPast.length === 0) {
        return null; // No past aufguss found
    }

    const lastAufgussDate = new Date(userAufguesseInPast[0].date);
    lastAufgussDate.setHours(0, 0, 0, 0); // Normalize last aufguss date

    const diffTime = today.getTime() - lastAufgussDate.getTime();
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    return diffDays;
};

// --- API CLIENT (Simulates Backend Communication) ---

const apiClient = {
    // Helper to simulate network latency
    _simulateDelay: (ms = 400) => new Promise(resolve => setTimeout(resolve, ms)),

    // Load all initial data from localStorage
    loadAllData: async function() {
        await this._simulateDelay();
        try {
            const initialUsers = safeJSONParse('users', MOCK_USERS);
            // Data migration for old status values
            const users = initialUsers.map(u => ({...u, status: u.status === 'pending_approval' ? 'active' : u.status}));
            
            return {
                users,
                posts: safeJSONParse('posts', MOCK_POSTS),
                festivals: safeJSONParse('festivals', MOCK_FESTIVALS),
                aufguesse: safeJSONParse('aufguesse', generateInitialAufguesse()),
                awards: safeJSONParse('awards', MOCK_AWARDS),
                aufgussTypes: safeJSONParse('aufgussTypes', DEFAULT_AUFGUSS_TYPES),
                availableQuals: safeJSONParse('availableQuals', DEFAULT_QUALIFICATIONS),
                registrationCode: localStorage.getItem('registrationCode') || '123456',
                selectedFestivalId: localStorage.getItem('selectedFestivalId') || null,
                persistedBackgrounds: safeJSONParse('persistedBackgrounds', {}),
            };
        } catch (error) {
            console.error("Critical error loading data from localStorage. Resetting to defaults.", error);
            // Fallback to mock data if localStorage is corrupted
            return {
                users: MOCK_USERS,
                posts: MOCK_POSTS,
                festivals: MOCK_FESTIVALS,
                aufguesse: generateInitialAufguesse(),
                awards: MOCK_AWARDS,
                aufgussTypes: DEFAULT_AUFGUSS_TYPES,
                availableQuals: DEFAULT_QUALIFICATIONS,
                registrationCode: '123456',
                selectedFestivalId: null,
                persistedBackgrounds: {},
            }
        }
    },

    // Generic save method
    saveData: async function(key: string, data: any) {
        await this._simulateDelay(50);
        localStorage.setItem(key, JSON.stringify(data));
    },

    // Specific save methods for better readability
    saveUsers: async function(data: User[]) { await this.saveData('users', data); },
    savePosts: async function(data: Post[]) { await this.saveData('posts', data); },
    saveFestivals: async function(data: Festival[]) { await this.saveData('festivals', data); },
    saveAufguesse: async function(data: Aufguss[]) { await this.saveData('aufguesse', data); },
    saveAwards: async function(data: Award[]) { await this.saveData('awards', data); },
    saveAufgussTypes: async function(data: string[]) { await this.saveData('aufgussTypes', data); },
    saveAvailableQuals: async function(data: string[]) { await this.saveData('availableQuals', data); },
    saveRegistrationCode: async function(code: string) {
        await this._simulateDelay(50);
        localStorage.setItem('registrationCode', code);
    },
    saveSelectedFestivalId: async function(id: string) {
        await this._simulateDelay(20);
        localStorage.setItem('selectedFestivalId', id);
    },
     saveBackgrounds: async function(backgrounds: Record<string, string>) {
        await this.saveData('persistedBackgrounds', backgrounds);
    }
};


// --- COMPONENTS ---

const LoginPage = ({ onLogin, onGoToRegister }: { onLogin: (username: string, pass: string) => void, onGoToRegister: () => void }) => {
    const [username, setUsername] = useState('admin');
    const [password, setPassword] = useState('password');

    return (
        <div className="login-container">
            <span className="material-icons-outlined" style={{ fontSize: '60px' }}>self_improvement</span>
            <h1>Saunafreunde Schwarzwald e.V.</h1>
            <p>Willkommen im Mitgliederbereich.</p>
            <div className="card login-form">
                <div className="form-group">
                    <input type="text" placeholder="Benutzername (z.B. admin)" value={username} onChange={e => setUsername(e.target.value)} />
                </div>
                <div className="form-group">
                    <input type="password" placeholder="Passwort (z.B. password)" value={password} onChange={e => setPassword(e.target.value)} />
                </div>
                <button className="login-btn" onClick={() => onLogin(username, password)}>Anmelden</button>
            </div>
            <p className="register-link">Noch kein Konto? <button onClick={onGoToRegister}>Jetzt registrieren</button></p>
        </div>
    )
};

const RegistrationPage = ({ code, onCodeSubmit, onBack }: { code: string, onCodeSubmit: (enteredCode: string) => void, onBack: () => void }) => {
    const [enteredCode, setEnteredCode] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = () => {
        if (enteredCode === code) {
            onCodeSubmit(enteredCode);
        } else {
            setError('Der Code ist ungültig. Bitte frage den Admin nach dem aktuellen Code.');
        }
    }

    return (
        <div className="login-container">
            <span className="material-icons-outlined" style={{ fontSize: '60px' }}>key</span>
            <h1>Mitglied werden</h1>
            <p>Bitte gib den 6-stelligen Vereinscode ein, um fortzufahren.</p>
            <div className="card login-form" style={{ maxWidth: '400px' }}>
                <div className="form-group">
                    <input
                        type="text"
                        placeholder="6-stelliger Code"
                        value={enteredCode}
                        onChange={(e) => setEnteredCode(e.target.value)}
                        maxLength={6}
                    />
                </div>
                 {error && <p className="error-message">{error}</p>}
                <button className="login-btn" onClick={handleSubmit}>Weiter</button>
            </div>
             <p className="register-link"><button onClick={onBack}>Zurück zum Login</button></p>
        </div>
    );
};

const ProfileSetupPage = ({ onCompleteRegistration, onBack }: { onCompleteRegistration: (newUser: Omit<User, 'id' | 'avatarUrl' | 'qualifications' | 'awards' | 'aufgussCount' | 'workHours' | 'isAdmin' | 'status' | 'shortNoticeCancellations' | 'showInMemberList' | 'permissions' | 'lastProfileUpdate' | 'lastAufgussShareTimestamp'>) => void, onBack: () => void }) => {
    const [formData, setFormData] = useState({
        name: '',
        nickname: '',
        email: '',
        phone: '',
        primarySauna: SAUNA_LOCATIONS[0],
        username: '',
        password: '',
        motto: '',
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };
    
    const handleSubmit = () => {
        if (!formData.name || !formData.email || !formData.username || !formData.password) {
            alert('Bitte fülle alle Pflichtfelder aus.');
            return;
        }
        onCompleteRegistration({
            name: formData.name,
            nickname: formData.nickname,
            email: formData.email,
            phone: formData.phone,
            primarySauna: formData.primarySauna,
            username: formData.username,
            motto: formData.motto,
        });
    };

    return (
         <div className="login-container profile-setup">
            <span className="material-icons-outlined" style={{ fontSize: '60px' }}>person_add</span>
            <h1>Profil einrichten</h1>
            <p>Fast geschafft! Bitte vervollständige deine Daten.</p>
            <div className="card login-form" style={{ maxWidth: '500px', textAlign: 'left' }}>
                <div className="form-group">
                    <label>Echter Name*</label>
                    <input type="text" name="name" value={formData.name} onChange={handleChange} required/>
                </div>
                 <div className="form-group">
                    <label>Spitzname (optional)</label>
                    <input type="text" name="nickname" value={formData.nickname} onChange={handleChange} />
                </div>
                <div className="form-group">
                    <label>Motto oder Slogan (optional)</label>
                    <textarea name="motto" value={formData.motto} onChange={handleChange} rows={2}/>
                </div>
                <div className="form-group">
                    <label>E-Mail*</label>
                    <input type="email" name="email" value={formData.email} onChange={handleChange} required/>
                </div>
                <div className="form-group">
                    <label>Telefon (optional)</label>
                    <input type="tel" name="phone" value={formData.phone} onChange={handleChange} />
                </div>
                <div className="form-group">
                    <label>Haupt-Sauna</label>
                    <select name="primarySauna" value={formData.primarySauna} onChange={handleChange}>
                        {SAUNA_LOCATIONS.map(loc => <option key={loc} value={loc}>{loc}</option>)}
                    </select>
                </div>
                <>
                    <div className="form-group">
                        <label>Benutzername*</label>
                        <input type="text" name="username" value={formData.username} onChange={handleChange} required/>
                    </div>
                    <div className="form-group">
                        <label>Passwort*</label>
                        <input type="password" name="password" value={formData.password} onChange={handleChange} required/>
                    </div>
                </>
                <button className="login-btn" onClick={handleSubmit}>Registrierung abschließen</button>
            </div>
             <p className="register-link"><button onClick={onBack}>Zurück zum Login</button></p>
        </div>
    )

};

const Header = React.memo(({ user, onLogout, setView, activeView }: { user: User, onLogout: () => void, setView: (view: View, userId?: number) => void, activeView: View }) => (
    <header className="app-header">
        <div className="logo">
            <span className="material-icons-outlined">self_improvement</span> Saunafreunde
        </div>
        <nav>
            <button onClick={() => setView('dashboard')} className={activeView === 'dashboard' ? 'active' : ''}>Dashboard</button>
            <button onClick={() => setView('social')} className={activeView === 'social' ? 'active' : ''}>Social</button>
            <button onClick={() => setView('aufguss')} className={activeView === 'aufguss' ? 'active' : ''}>Aufgussplan</button>
            <button onClick={() => setView('festival')} className={activeView === 'festival' ? 'active' : ''}>Saunafest</button>
            <button onClick={() => setView('mitglieder')} className={activeView === 'mitglieder' ? 'active' : ''}>Mitglieder</button>
            {user.isAdmin && <button onClick={() => setView('berichte')} className={activeView === 'berichte' ? 'active' : ''}>Berichte</button>}
            <button onClick={() => setView('profile', user.id)} className={activeView === 'profile' ? 'active' : ''}>Mein Profil</button>
            <a href="https://aromen123.de" target="_blank" rel="noopener noreferrer" className="partner-shop-btn">
                 <span className="material-icons-outlined">storefront</span>
                 Partner-Shop
            </a>
            <button onClick={onLogout} className="logout-button">Logout</button>
        </nav>
    </header>
));

const CountdownTimer = ({ targetDate, onEnd }: { targetDate: string, onEnd: () => void }) => {
    const calculateTimeLeft = useCallback(() => {
        const difference = +new Date(targetDate) - +new Date();
        let timeLeft = {};

        if (difference > 0) {
            timeLeft = {
                Tage: Math.floor(difference / (1000 * 60 * 60 * 24)),
                Stunden: Math.floor((difference / (1000 * 60 * 60)) % 24),
                Minuten: Math.floor((difference / 1000 / 60) % 60),
                Sekunden: Math.floor((difference / 1000) % 60)
            };
        } else {
            onEnd();
        }
        return timeLeft;
    }, [targetDate, onEnd]);

    const [timeLeft, setTimeLeft] = useState(calculateTimeLeft());

    useEffect(() => {
        const timer = setTimeout(() => {
            setTimeLeft(calculateTimeLeft());
        }, 1000);

        return () => clearTimeout(timer);
    });

    const timerComponents = Object.entries(timeLeft).map(([interval, value]) => {
        if (value === undefined) return null;
        return (
            <div key={interval} className="countdown-item">
                <span className="countdown-value">{String(value).padStart(2, '0')}</span>
                <span className="countdown-label">{interval}</span>
            </div>
        );
    }).filter(Boolean);

    return (
        <div className="countdown-container">
            {timerComponents.length ? timerComponents : <span>Zeit abgelaufen!</span>}
        </div>
    );
};


const Dashboard = ({ user, setView, allUsers, allAufguesse, festivals, registrationCode, onGenerateCode, persistedBackgrounds, onUploadBackground, onRemoveBackground }: { user: User, setView: (view: View, userId?: number) => void, allUsers: User[], allAufguesse: Aufguss[], festivals: Festival[], registrationCode: string, onGenerateCode: () => void, persistedBackgrounds: Record<string, string>, onUploadBackground: (viewKey: string, file: File) => Promise<void>, onRemoveBackground: (viewKey: string) => Promise<void> }) => {
    const [uploading, setUploading] = useState<string | null>(null);
    
    const aufgussActivity = useMemo(() => {
        return allUsers
            .filter(u => !u.isAdmin && u.status === 'active')
            .map(u => ({
                user: u,
                daysSince: calculateDaysSinceLastAufguss(u.id, allAufguesse)
            }))
            .sort((a, b) => {
                if (a.daysSince === null) return 1; // Put users with no aufguss at the end
                if (b.daysSince === null) return -1;
                return b.daysSince - a.daysSince; // Sort by most days descending
            });
    }, [allUsers, allAufguesse]);

    const festivalForRsvp = useMemo(() => {
        return festivals.find(f => {
            const myParticipation = f.participants.find(p => p.userId === user.id);
            return myParticipation?.status === 'pending' && new Date(f.rsvpDeadline) > new Date();
        });
    }, [festivals, user.id]);

    const [, forceUpdate] = useState({}); // To re-render when timer ends

    const handleFileChange = async (viewKey: string, e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploading(viewKey);
        try {
            await onUploadBackground(viewKey, file);
        } catch (error) {
            console.error("Error uploading background:", error);
            alert("Fehler beim Hochladen des Bildes.");
        } finally {
            setUploading(null);
            // Clear the input value so the same file can be selected again
            e.target.value = '';
        }
    };
    
    const VIEW_NAMES: Record<string, string> = {
        login: "Login",
        register: "Registrierung",
        profile_setup: "Profil-Einrichtung",
        dashboard: "Dashboard",
        social: "Social Feed",
        aufguss: "Aufgussplaner",
        festival: "Saunafest",
        mitglieder: "Mitglieder",
        berichte: "Berichte",
        profile: "Profil",
        nikolaus: "Nikolaus (Saisonal)",
        christmas: "Weihnachten (Saisonal)",
        silvester: "Silvester (Saisonal)",
        easter: "Ostern (Saisonal)"
    };

    return (
        <div className="container">
            <h2>Willkommen zurück, {user.name.split(' ')[0]}!</h2>
            <div className="grid-container dashboard-grid">
                {festivalForRsvp && (
                    <div className="card full-width-card rsvp-reminder-card">
                        <h3><span className="material-icons-outlined">event_available</span> Rückmeldung für "{festivalForRsvp.name}"</h3>
                        <p>Bitte gib bis zur Deadline an, ob du teilnimmst und wann du für Aufgüsse verfügbar wärst.</p>
                        <CountdownTimer targetDate={festivalForRsvp.rsvpDeadline} onEnd={() => forceUpdate({})} />
                        <button onClick={() => setView('festival')} className="link-button" style={{marginTop: '1.5rem'}}>Zur Festival-Planung</button>
                    </div>
                )}
                {user.isAdmin && (
                    <div className="card">
                        <h3>Vereins-Code für Neumitglieder</h3>
                        <div className="code-display-container">
                            <span className="registration-code">{registrationCode}</span>
                            <button className="regenerate-btn" onClick={onGenerateCode} title="Neuen Code generieren">
                                <span className="material-icons-outlined">refresh</span>
                            </button>
                        </div>
                    </div>
                )}
                 <div className="card">
                    <h3>Deine Statistik</h3>
                    <p>Du hast bereits <strong>{user.aufgussCount}</strong> Aufgüsse durchgeführt und <strong>{user.workHours}</strong> Arbeitsstunden geleistet. Weiter so!</p>
                     <button onClick={() => setView('profile', user.id)} className="link-button">Zum Profil</button>
                </div>
                {user.isAdmin && (
                     <div className="card full-width-card">
                         <h3>Hintergrundbilder verwalten</h3>
                         <div className="background-manager">
                            {Object.keys(VIEW_NAMES).map(viewKey => (
                                <div key={viewKey} className="background-manager-item">
                                    <img src={persistedBackgrounds[viewKey] || FALLBACK_BACKGROUND_URLS[viewKey] || ''} alt={`${VIEW_NAMES[viewKey]} thumbnail`} className="background-thumbnail"/>
                                    <span className="background-view-name">{VIEW_NAMES[viewKey]}</span>
                                    <div className="background-manager-actions">
                                        <input
                                            type="file"
                                            accept="image/*"
                                            id={`upload-${viewKey}`}
                                            style={{ display: 'none' }}
                                            onChange={(e) => handleFileChange(viewKey, e)}
                                            disabled={uploading === viewKey}
                                        />
                                        <label htmlFor={`upload-${viewKey}`} className={`upload-btn ${uploading === viewKey ? 'loading' : ''}`}>
                                            {uploading === viewKey ? (
                                                <div className="spinner-small"></div>
                                            ) : (
                                                <>
                                                    <span className="material-icons-outlined">upload</span>
                                                    <span>{persistedBackgrounds[viewKey] ? 'Ändern' : 'Hochladen'}</span>
                                                </>
                                            )}
                                        </label>
                                        {persistedBackgrounds[viewKey] && (
                                            <button className="remove-btn" onClick={() => onRemoveBackground(viewKey)}>
                                                <span className="material-icons-outlined">delete</span>
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                         </div>
                     </div>
                )}
                 {user.isAdmin && (
                    <div className="card full-width-card">
                        <h3>Aufguss-Aktivität</h3>
                        <ul className="admin-user-list">
                            {aufgussActivity.map(({user, daysSince}) => (
                                <li key={user.id}>
                                    <span>{user.name}</span>
                                    <span className={daysSince !== null && daysSince > 30 ? 'cancellations-warning' : ''}>
                                        {daysSince !== null ? `Letzter Aufguss: vor ${daysSince} Tagen` : 'Noch kein Aufguss'}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
                 {user.isAdmin && (
                    <div className="card full-width-card">
                        <h3>Admin-Übersicht: Kurzfristige Absagen</h3>
                        <ul className="admin-user-list">
                            {allUsers.filter(u => !u.isAdmin).sort((a,b) => b.shortNoticeCancellations - a.shortNoticeCancellations).map(u => (
                                <li key={u.id}>
                                    <span>{u.name}</span>
                                    <span className={u.shortNoticeCancellations > 0 ? 'cancellations-warning' : ''}>
                                        {u.shortNoticeCancellations} Absage(n)
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
};

const renderAvatar = (avatarUrl: string, name: string, className: string) => {
    const isEmoji = EMOJI_AVATARS.includes(avatarUrl) || (avatarUrl.length <= 2 && /\p{Emoji}/u.test(avatarUrl));
    if (isEmoji) {
        return <div className={`emoji-avatar-container ${className}`}><span className="emoji-avatar">{avatarUrl}</span></div>;
    }
    return <img src={avatarUrl} alt={name} className={`image-avatar ${className}`} />;
};

const ProfilePage = ({ currentUser, viewedUser, onUpdateUser, allAufguesse, allAwards, onBackToList }: { 
    currentUser: User;
    viewedUser: User;
    onUpdateUser: (updatedData: Partial<User>) => void;
    allAufguesse: Aufguss[];
    allAwards: Award[];
    onBackToList?: () => void;
}) => {
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

    const [isEditing, setIsEditing] = useState(false);
    const [formData, setFormData] = useState({
        name: viewedUser.name,
        nickname: viewedUser.nickname || '',
        phone: viewedUser.phone || '',
        primarySauna: viewedUser.primarySauna,
        motto: viewedUser.motto || '',
        avatarUrl: viewedUser.avatarUrl,
    });
    const [avatarEditMode, setAvatarEditMode] = useState<'image' | 'emoji'>('image');
    const [isCompressingAvatar, setIsCompressingAvatar] = useState(false);
    
    const isOwnProfile = currentUser.id === viewedUser.id;

    const daysSinceLastAufguss = useMemo(() => calculateDaysSinceLastAufguss(viewedUser.id, allAufguesse), [viewedUser.id, allAufguesse]);

    useEffect(() => {
        // Reset form if user data changes from props
        setFormData({
            name: viewedUser.name,
            nickname: viewedUser.nickname || '',
            phone: viewedUser.phone || '',
            primarySauna: viewedUser.primarySauna,
            motto: viewedUser.motto || '',
            avatarUrl: viewedUser.avatarUrl,
        });
        setIsEditing(false); // Exit edit mode when viewing a new profile
    }, [viewedUser]);

    // 30-day lock logic
    const thirtyDaysInMillis = 30 * 24 * 60 * 60 * 1000;
    const lastUpdate = viewedUser.lastProfileUpdate || 0;
    const canEdit = Date.now() - lastUpdate > thirtyDaysInMillis;
    const nextEditDate = new Date(lastUpdate + thirtyDaysInMillis).toLocaleDateString('de-DE');

    const handleEditToggle = () => {
        if (!isEditing) { // Entering edit mode
            setIsEditing(true);
        } else { // Canceling edit mode
            setIsEditing(false);
            setFormData({ // Reset form data to original user data
                name: viewedUser.name,
                nickname: viewedUser.nickname || '',
                phone: viewedUser.phone || '',
                primarySauna: viewedUser.primarySauna,
                motto: viewedUser.motto || '',
                avatarUrl: viewedUser.avatarUrl,
            });
        }
    };

    const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleAvatarImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setIsCompressingAvatar(true);
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                const SIZE = 200;
                canvas.width = SIZE;
                canvas.height = SIZE;
                const ctx = canvas.getContext('2d');
                if (!ctx) {
                    setIsCompressingAvatar(false);
                    return;
                }

                // Draw image centered and cropped to a square
                const sourceRatio = img.width / img.height;
                let sourceX = 0, sourceY = 0, sourceWidth = img.width, sourceHeight = img.height;

                if (sourceRatio > 1) { // Wider than tall
                    sourceWidth = img.height;
                    sourceX = (img.width - sourceWidth) / 2;
                } else { // Taller than wide
                    sourceHeight = img.width;
                    sourceY = (img.height - sourceHeight) / 2;
                }

                ctx.drawImage(img, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, SIZE, SIZE);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.85); // 85% quality JPEG
                setFormData(prev => ({ ...prev, avatarUrl: dataUrl }));
                setIsCompressingAvatar(false);
            };
            img.src = e.target?.result as string;
        };
        reader.readAsDataURL(file);
    };


    const handleSave = () => {
        if (!formData.name.trim()) {
            alert('Der Name darf nicht leer sein.');
            return;
        }
        onUpdateUser({
            ...formData, // Send all form data
            lastProfileUpdate: Date.now()
        });
        setIsEditing(false);
    };

    const handlePasswordChange = () => {
        setMessage(null);
        if(!oldPassword || !newPassword || !confirmPassword) {
            setMessage({type: 'error', text: 'Bitte alle Felder ausfüllen.'});
            return;
        }
        if (newPassword !== confirmPassword) {
            setMessage({type: 'error', text: 'Die neuen Passwörter stimmen nicht überein.'});
            return;
        }
        console.log(`Password change for ${viewedUser.username} to ${newPassword}`);
        setMessage({type: 'success', text: 'Dein Passwort wurde erfolgreich geändert.'});
        setOldPassword('');
        setNewPassword('');
        setConfirmPassword('');
    };
    
    const avatarFileInputRef = React.useRef<HTMLInputElement>(null);

    return (
        <div className="container">
            {onBackToList && (
                 <button onClick={onBackToList} className="back-to-list-btn">
                     <span className="material-icons-outlined">arrow_back</span> Zurück zur Mitgliederliste
                 </button>
            )}
            <h2>{isOwnProfile ? "Mein Profil" : `Profil von ${viewedUser.name}`}</h2>
            <div className="grid-container profile-grid">
                <div className="card">
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem', marginBottom: '1rem' }}>
                         <h3 style={{marginBottom: 0, borderBottom: 'none'}}>{isOwnProfile ? "Meine Daten & Einstellungen" : "Profildaten"}</h3>
                         {isOwnProfile && (isEditing ? (
                             <div style={{display: 'flex', gap: '10px'}}>
                                 <button onClick={handleEditToggle} className="cancel-btn">Abbrechen</button>
                                 <button onClick={handleSave} className="save-btn">Speichern</button>
                             </div>
                         ) : (
                             <button onClick={handleEditToggle} disabled={!canEdit} className="admin-btn" title={!canEdit ? `Bearbeitung wieder möglich am ${nextEditDate}` : 'Profil bearbeiten'}>
                                 Bearbeiten
                             </button>
                         ))}
                    </div>

                    {isOwnProfile && !canEdit && !isEditing && (
                        <p className="info-message" style={{marginBottom: '1rem'}}>Du kannst dein Profil wieder am {nextEditDate} bearbeiten.</p>
                    )}
                    
                    {isEditing && isOwnProfile ? (
                        <div className="profile-form">
                             <div className="form-group">
                                <label>Echter Name</label>
                                <input type="text" name="name" value={formData.name} onChange={handleFormChange} required />
                            </div>
                            <div className="form-group">
                                <label>Spitzname (optional)</label>
                                <input type="text" name="nickname" value={formData.nickname} onChange={handleFormChange} />
                            </div>
                            <div className="form-group">
                                <label>Motto (optional)</label>
                                <textarea name="motto" value={formData.motto} onChange={handleFormChange} rows={2} />
                            </div>
                            <div className="form-group">
                                <label>Telefon (optional)</label>
                                <input type="tel" name="phone" value={formData.phone} onChange={handleFormChange} />
                            </div>
                            <div className="form-group">
                                <label>Haupt-Sauna</label>
                                <select name="primarySauna" value={formData.primarySauna} onChange={handleFormChange}>
                                    {SAUNA_LOCATIONS.map(loc => <option key={loc} value={loc}>{loc}</option>)}
                                </select>
                            </div>
                        </div>
                    ) : (
                         <div className="profile-data">
                            <p><strong>E-Mail:</strong> {viewedUser.email}</p>
                            <p><strong>Telefon:</strong> {viewedUser.phone || 'Keine Nummer angegeben'}</p>
                            <p><strong>Haupt-Sauna:</strong> {viewedUser.primarySauna}</p>
                        </div>
                    )}
                    
                    
                    <div className="profile-data" style={{marginTop: '2rem'}}>
                        <h4>Qualifikationen</h4>
                        {viewedUser.qualifications.length > 0 ? 
                            <ul>{viewedUser.qualifications.map(q => <li key={q}>{q}</li>)}</ul> :
                            <p>Keine Qualifikationen eingetragen.</p>
                        }
                    </div>
                    {isOwnProfile && (
                        <div className="profile-settings" style={{marginTop: '2rem'}}>
                            <h4>Sichtbarkeit</h4>
                                <div className="form-group">
                                    <label className="checkbox-label" style={{justifyContent: 'flex-start'}}>
                                    <input
                                        type="checkbox"
                                        checked={viewedUser.showInMemberList}
                                        onChange={(e) => onUpdateUser({ showInMemberList: e.target.checked })}
                                    />
                                    Mein Profil im Mitgliederverzeichnis anzeigen
                                </label>
                            </div>
                        </div>
                    )}
                </div>

                <div className="card">
                    <div className="profile-header">
                        {renderAvatar(isEditing ? formData.avatarUrl : viewedUser.avatarUrl, viewedUser.name, 'profile-avatar')}
                        <div>
                            <h3>{viewedUser.name} {viewedUser.nickname && `(${viewedUser.nickname})`}</h3>
                            {viewedUser.motto && <p className="profile-motto">"{viewedUser.motto}"</p>}
                             {!isOwnProfile && <p>{viewedUser.email}</p>}
                        </div>
                    </div>

                    {isEditing && isOwnProfile && (
                        <div className="avatar-editor">
                            <div className="post-mode-switcher">
                                <button onClick={() => setAvatarEditMode('image')} className={avatarEditMode === 'image' ? 'active' : ''}>Bild</button>
                                <button onClick={() => setAvatarEditMode('emoji')} className={avatarEditMode === 'emoji' ? 'active' : ''}>Emoji</button>
                            </div>
                            {avatarEditMode === 'image' && (
                                <>
                                    <input type="file" accept="image/*" ref={avatarFileInputRef} onChange={handleAvatarImageChange} style={{display: 'none'}} id="avatar-upload-input"/>
                                    <label htmlFor="avatar-upload-input" className={`image-upload-label ${isCompressingAvatar ? 'disabled' : ''}`}>
                                        <span className="material-icons-outlined">add_photo_alternate</span>
                                        {isCompressingAvatar ? 'Bild wird verarbeitet...' : 'Neues Bild auswählen'}
                                    </label>
                                </>
                            )}
                            {avatarEditMode === 'emoji' && (
                                <div className="emoji-grid">
                                    {EMOJI_AVATARS.map(emoji => (
                                        <button key={emoji} className={`emoji-option ${formData.avatarUrl === emoji ? 'selected' : ''}`} onClick={() => setFormData({...formData, avatarUrl: emoji})}>
                                            {emoji}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}


                    <div className="profile-stats">
                        <div className="stat-item">
                            <div className="value">{viewedUser.aufgussCount}</div>
                            <div className="label">Geleistete Aufgüsse</div>
                        </div>
                        <div className="stat-item">
                            <div className="value">{viewedUser.workHours}</div>
                            <div className="label">Arbeitsstunden</div>
                        </div>
                         <div className="stat-item">
                            <div className="value">{viewedUser.awards.length}</div>
                            <div className="label">Auszeichnungen</div>
                        </div>
                         <div className="stat-item">
                            <div className="value">{daysSinceLastAufguss !== null ? daysSinceLastAufguss : '-'}</div>
                            <div className="label">Tage ohne Aufguss</div>
                        </div>
                    </div>
                </div>
            
                <div className="card full-width-card">
                    <h3>Auszeichnungen</h3>
                    <div className="achievements-grid">
                        {viewedUser.awards.length > 0 ? viewedUser.awards.map(awardId => {
                            const award = allAwards.find(a => a.id === awardId);
                            if (!award) return null;
                            return (
                                <div key={award.id} className="achievement">
                                    <span className="material-icons-outlined" style={{color: award.color}}>{award.icon}</span>
                                    <span>{award.name}</span>
                                </div>
                            );
                        }) : <p>Sammle mehr Erfahrung für Auszeichnungen!</p>}
                    </div>
                </div>

                 {isOwnProfile && (
                    <div className="card full-width-card">
                        <h3>Passwort ändern</h3>
                        <div className="form-group">
                            <label>Altes Passwort</label>
                            <input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} />
                        </div>
                         <div className="form-group">
                            <label>Neues Passwort</label>
                            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} />
                        </div>
                         <div className="form-group">
                            <label>Neues Passwort bestätigen</label>
                            <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
                        </div>
                        {message && <p className={`${message.type}-message`}>{message.text}</p>}
                        <button className="save-btn" onClick={handlePasswordChange}>Passwort speichern</button>
                    </div>
                 )}
            </div>
        </div>
    );
}

const AufgussTypeManagementModal = ({ isOpen, onClose, types, onAddType, onDeleteType, onRenameType }) => {
    const [newItem, setNewItem] = useState('');
    const [editingItem, setEditingItem] = useState(null);
    const [editingText, setEditingText] = useState('');

    if (!isOpen) return null;

    const handleAdd = () => {
        if (newItem.trim()) {
            onAddType(newItem.trim());
            setNewItem('');
        }
    };

    const startEditing = (type) => {
        setEditingItem(type);
        setEditingText(type);
    };

    const handleRename = () => {
        if (editingText.trim() && editingItem) {
            onRenameType(editingItem, editingText.trim());
        }
        setEditingItem(null);
        setEditingText('');
    };
    
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <h3>Aufgussarten verwalten</h3>
                <div className="editable-list">
                    {types.map(type => (
                        <div key={type} className="editable-list-item">
                            {editingItem === type ? (
                                <div className="editable-list-item-content">
                                    <input 
                                        type="text" 
                                        value={editingText} 
                                        onChange={e => setEditingText(e.target.value)}
                                        onBlur={handleRename}
                                        onKeyDown={e => e.key === 'Enter' && handleRename()}
                                        autoFocus
                                    />
                                </div>
                            ) : (
                                <span className="editable-list-item-content">{type}</span>
                            )}
                            <div className="editable-list-item-actions">
                                <button onClick={() => startEditing(type)} title="Umbenennen"><span className="material-icons-outlined">edit</span></button>
                                <button onClick={() => onDeleteType(type)} title="Löschen"><span className="material-icons-outlined">delete</span></button>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="editable-list-form">
                    <input 
                        type="text" 
                        placeholder="Neue Aufgussart..." 
                        value={newItem}
                        onChange={e => setNewItem(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleAdd()}
                    />
                    <button className="save-btn" onClick={handleAdd}>Hinzufügen</button>
                </div>
                <div className="modal-actions" style={{justifyContent: 'center'}}>
                    <button className="cancel-btn" onClick={onClose}>Schließen</button>
                </div>
            </div>
        </div>
    );
};

const AufgussPlanner = ({ user, aufguesse, aufgussTypes, onClaimAufguss, onCancelAufguss, onShareAufguss, onManageAufgussTypes }) => {
    const today = new Date();
    const [selectedDate, setSelectedDate] = useState(today.toISOString().split('T')[0]);
    const [selectedLocation, setSelectedLocation] = useState(SAUNA_LOCATIONS[0]);
    
    // Modals
    const [typeModalOpen, setTypeModalOpen] = useState(false);
    const [shareModalOpen, setShareModalOpen] = useState(false);
    const [manageTypesModalOpen, setManageTypesModalOpen] = useState(false);

    const [selectedAufguss, setSelectedAufguss] = useState<Aufguss | null>(null);
    const [selectedType, setSelectedType] = useState(aufgussTypes[0] || '');

    useEffect(() => {
      if (aufgussTypes.length > 0 && !aufgussTypes.includes(selectedType)) {
        setSelectedType(aufgussTypes[0]);
      }
    }, [aufgussTypes, selectedType]);


    const handleDateChange = (direction: number) => {
        const currentDate = new Date(selectedDate);
        currentDate.setDate(currentDate.getDate() + direction);
        const maxDate = new Date();
        maxDate.setDate(today.getDate() + 29);

        if (currentDate >= today && currentDate <= maxDate) {
             setSelectedDate(currentDate.toISOString().split('T')[0]);
        }
    };
    
    const handleClaimClick = (aufguss: Aufguss) => {
        setSelectedAufguss(aufguss);
        setTypeModalOpen(true);
    };

    const handleConfirmClaim = () => {
        if (selectedAufguss && selectedType) {
            onClaimAufguss(selectedAufguss.id, selectedType);
            // Open the share modal right after claiming
            setSelectedAufguss({...selectedAufguss, type: selectedType });
            setShareModalOpen(true);
             setTypeModalOpen(false);
        } else {
            alert("Bitte eine Aufgussart auswählen.");
        }
    };

    const handleShareClick = () => {
        if(selectedAufguss) {
            onShareAufguss(selectedAufguss);
        }
        setShareModalOpen(false);
        setSelectedAufguss(null);
    }
    
    const formattedDate = new Date(selectedDate).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    const slotsForDateAndLocation = aufguesse.filter(a => a.date === selectedDate && a.location === selectedLocation);

    const renderSchedule = () => {
        if (selectedLocation === SAUNA_LOCATIONS[2]) {
             const hoechenschwandClosureDate = new Date(new Date().getFullYear(), 7, 31);
             if (new Date(selectedDate) <= hoechenschwandClosureDate) {
                 return <p className="info-message">Die Saunawelt Höchenschwand ist bis Ende August geschlossen.</p>
             }
        }
        
        if (slotsForDateAndLocation.length === 0) {
            return <p className="info-message">Für diesen Tag sind an diesem Standort keine Aufgüsse geplant.</p>;
        }

        const saunasForLocation = LOCATION_SAUNAS[selectedLocation] || [];

        return (
            <div className="aufguss-schedule">
                {saunasForLocation.map(saunaName => {
                    const slotsForSauna = slotsForDateAndLocation.filter(a => a.sauna === saunaName);
                    if (slotsForSauna.length === 0) return null;
                    return (
                        <div key={saunaName} className="sauna-card">
                            <h4>{saunaName}</h4>
                            <div className="slots-container">
                                {slotsForSauna.map(slot => {
                                    const isYours = slot.aufgussmeisterId === user.id;
                                    const isTaken = !!slot.aufgussmeisterId;
                                    let slotClass = "aufguss-slot";
                                    if (isYours) slotClass += " yours";
                                    else if (isTaken) slotClass += " taken";
                                    else slotClass += " available";

                                    return (
                                        <div key={slot.id} className={slotClass}>
                                            <div className="slot-time">{slot.time}</div>
                                            <div className="slot-details">
                                                {isTaken ? (
                                                    <>
                                                        <span className="meister">{slot.aufgussmeisterName?.split(' ')[0]}</span>
                                                        <span className="type">{slot.type}</span>
                                                    </>
                                                ) : <span>Frei</span>}
                                            </div>
                                            <div className="slot-action">
                                                {!isTaken && <button className="claim-btn" onClick={() => handleClaimClick(slot)}>Übernehmen</button>}
                                                {(user.isAdmin || isYours) && isTaken && (
                                                    <button className="cancel-aufguss-btn" title="Aufguss stornieren" onClick={() => onCancelAufguss(slot.id)}>
                                                        <span className="material-icons-outlined">delete</span>
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                             </div>
                        </div>
                    );
                })}
            </div>
        );
    }

    const canShare = !user.lastAufgussShareTimestamp || (Date.now() - user.lastAufgussShareTimestamp > 24 * 60 * 60 * 1000);

    return (
        <div className="container">
            <div className="planner-controls card">
                <h2 className="planner-title">Aufgussplaner</h2>
                <div className="date-nav">
                    <button onClick={() => handleDateChange(-1)} title="Vorheriger Tag">
                        <span className="material-icons-outlined">chevron_left</span>
                    </button>
                    <span className="current-date">{formattedDate}</span>
                    <button onClick={() => handleDateChange(1)} title="Nächster Tag">
                        <span className="material-icons-outlined">chevron_right</span>
                    </button>
                </div>
                 <div className="location-tabs">
                    {SAUNA_LOCATIONS.map(loc => (
                        <button 
                            key={loc} 
                            className={`location-tab ${selectedLocation === loc ? 'active' : ''}`}
                            onClick={() => setSelectedLocation(loc)}
                        >
                            {loc}
                        </button>
                    ))}
                </div>
            </div>

            {renderSchedule()}

            {typeModalOpen && (
                <div className="modal-overlay">
                    <div className="modal-content">
                        <h3>
                            Aufgussart wählen
                            {user.isAdmin && <button className="admin-btn" onClick={() => { setTypeModalOpen(false); setManageTypesModalOpen(true);}}>Verwalten</button>}
                        </h3>
                        <div className="form-group">
                            <label htmlFor="aufguss-type">Bitte wähle die Art des Aufgusses:</label>
                            <select id="aufguss-type" value={selectedType} onChange={e => setSelectedType(e.target.value)}>
                                {aufgussTypes.length > 0 ? aufgussTypes.map(type => <option key={type} value={type}>{type}</option>) : <option disabled>Keine Arten verfügbar</option>}
                            </select>
                        </div>
                        <div className="modal-actions">
                            <button className="cancel-btn" onClick={() => setTypeModalOpen(false)}>Abbrechen</button>
                            <button className="save-btn" onClick={handleConfirmClaim} disabled={aufgussTypes.length === 0}>Bestätigen</button>
                        </div>
                    </div>
                </div>
            )}
            
            {user.isAdmin && (
                <AufgussTypeManagementModal 
                    isOpen={manageTypesModalOpen}
                    onClose={() => setManageTypesModalOpen(false)}
                    types={aufgussTypes}
                    {...onManageAufgussTypes}
                />
            )}

            {shareModalOpen && (
                 <div className="modal-overlay">
                    <div className="modal-content">
                        <h3><span className="material-icons-outlined" style={{verticalAlign: 'bottom', color: 'var(--success-color)'}}>check_circle</span> Aufguss übernommen!</h3>
                        <p>Dein Aufguss wurde erfolgreich im Plan eingetragen. Möchtest du es im Feed teilen?</p>
                        <div className="modal-actions">
                            <button className="cancel-btn" onClick={() => {setShareModalOpen(false); setSelectedAufguss(null);}}>Schließen</button>
                            <button 
                                className="save-btn"
                                onClick={handleShareClick}
                                disabled={!canShare}
                                title={!canShare ? 'Du kannst nur alle 24 Stunden einen Aufguss teilen.' : 'Im Feed teilen'}
                            >
                                Im Feed teilen
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const FestivalPlanner = ({ user, users, festivals, selectedFestivalId, onSelectFestival, onUpdateFestival, onCreateFestival, onDeleteFestival, onLogHours }: { 
    user: User;
    users: User[];
    festivals: Festival[];
    selectedFestivalId: string;
    onSelectFestival: (id: string) => void;
    onUpdateFestival: (festival: Festival) => void;
    onCreateFestival: (festivalData: Omit<Festival, 'id' | 'participants' | 'tasks' | 'rsvpDeadline'>) => void;
    onDeleteFestival: (festivalId: string) => void;
    onLogHours: (festivalId: string, hours: number) => void;
}) => {
    const [taskModalOpen, setTaskModalOpen] = useState(false);
    const [newTaskDesc, setNewTaskDesc] = useState("");

    const [formMode, setFormMode] = useState<'create' | 'edit' | null>(null);
    const [formData, setFormData] = useState<Partial<Festival> | null>(null);
    const [timeGenData, setTimeGenData] = useState({ start: '10:00', end: '22:00', interval: '60' });
    
    const [adminView, setAdminView] = useState('planung');
    const [loggedHours, setLoggedHours] = useState<string>('');
    
    const canCreateFestivals = user.isAdmin || user.permissions.includes('create_festivals');
    const selectedFestival = festivals.find(f => f.id === selectedFestivalId);
    
    const myParticipation = useMemo(() => selectedFestival?.participants?.find(p => p.userId === user.id), [selectedFestival, user.id]);
    const [proposals, setProposals] = useState(myParticipation?.aufgussProposals ?? []);
    
     useEffect(() => {
        if (selectedFestival) {
            const currentParticipation = selectedFestival.participants?.find(p => p.userId === user.id);
            setProposals(currentParticipation?.aufgussProposals ?? []);
        }
    }, [selectedFestival, user.id]);

    const handleUpdate = (updatedFestival: Festival) => {
        onUpdateFestival(updatedFestival);
    };

    const handleRsvp = (status: 'attending' | 'not_attending') => {
        if (!selectedFestival) return;
        const updatedParticipants = (selectedFestival.participants ?? []).map(p =>
            p.userId === user.id ? { ...p, status } : p
        );
        handleUpdate({ ...selectedFestival, participants: updatedParticipants });
    };
    
    const handleAvailabilityChange = (time: string, checked: boolean) => {
        if (!selectedFestival) return;
        const updatedParticipants = (selectedFestival.participants ?? []).map(p => {
            if (p.userId === user.id) {
                const currentAvailability = p.aufgussAvailability ?? [];
                const newAvailability = checked
                    ? [...currentAvailability, time].sort()
                    : currentAvailability.filter(t => t !== time);
                return { ...p, aufgussAvailability: newAvailability };
            }
            return p;
        });
        handleUpdate({ ...selectedFestival, participants: updatedParticipants });
    };
    
    const handleTaskClaim = (taskId: number) => {
        if (!selectedFestival) return;
        const updatedTasks = (selectedFestival.tasks ?? []).map(t =>
            t.id === taskId ? { ...t, responsible: user.id } : t
        );
        handleUpdate({ ...selectedFestival, tasks: updatedTasks });
    };

    const handleTaskRelease = (taskId: number) => {
        if (!selectedFestival) return;
        const updatedTasks = (selectedFestival.tasks ?? []).map(t =>
            t.id === taskId ? { ...t, responsible: null } : t
        );
        handleUpdate({ ...selectedFestival, tasks: updatedTasks });
    };
    
    const handleAdminTaskAssign = (taskId: number, responsibleId: string) => {
         if (!selectedFestival) return;
        const updatedTasks = (selectedFestival.tasks ?? []).map(t =>
            t.id === taskId ? { ...t, responsible: responsibleId ? Number(responsibleId) : null } : t
        );
        handleUpdate({ ...selectedFestival, tasks: updatedTasks });
    };

    const handleAddTask = () => {
        if (newTaskDesc.trim() && selectedFestival) {
            const newTask: FestivalTask = {
                id: Date.now(),
                description: newTaskDesc.trim(),
                responsible: null,
            };
            handleUpdate({ ...selectedFestival, tasks: [...(selectedFestival.tasks ?? []), newTask] });
            setNewTaskDesc("");
            setTaskModalOpen(false);
        }
    };

    const handleLogHoursSubmit = () => {
        const hours = parseInt(loggedHours, 10);
        if(!isNaN(hours) && hours > 0) {
            onLogHours(selectedFestivalId, hours);
            setLoggedHours('');
        }
    };
    
    const handleProposalCountChange = (count: number) => {
        const newCount = Math.max(0, count);
        const currentCount = proposals.length;
        if (newCount > currentCount) {
            const newItems = Array.from({ length: newCount - currentCount }, (_, i) => ({ id: `new_${Date.now()}_${Math.random() + i}`, name: '' }));
            setProposals([...proposals, ...newItems]);
        } else if (newCount < currentCount) {
            setProposals(proposals.slice(0, newCount));
        }
    };

    const handleProposalNameChange = (index: number, name: string) => {
        const newProposals = [...proposals];
        newProposals[index] = { ...newProposals[index], name };
        setProposals(newProposals);
    };

    const handleSaveProposals = () => {
        if (!selectedFestival) return;
        const finalProposals = proposals
            .map(p => ({
                id: p.id.startsWith('new_') ? `prop_${Date.now()}_${Math.random()}` : p.id,
                name: p.name
            }));

        const updatedParticipants = (selectedFestival.participants ?? []).map(p =>
            p.userId === user.id ? { ...p, aufgussProposals: finalProposals } : p
        );
        handleUpdate({ ...selectedFestival, participants: updatedParticipants });
        alert('Deine Aufguss-Angebote wurden gespeichert!');
    };
    
    // --- New Form Handlers ---
    const handleOpenCreateForm = () => {
        const today = new Date().toISOString().split('T')[0];
        setFormData({
            name: '',
            startDate: today,
            endDate: today,
            location: SAUNA_LOCATIONS[0],
            numberOfSaunas: 2,
            aufgussTimes: [],
        });
        setFormMode('create');
    };

    const handleOpenEditForm = () => {
        if (!selectedFestival) return;
        setFormData(selectedFestival);
        setFormMode('edit');
    };

    const handleCancelForm = () => {
        setFormMode(null);
        setFormData(null);
    };

    const handleSaveForm = () => {
        if (!formData || !formData.name || !formData.startDate || !formData.endDate) {
            alert("Bitte fülle alle Pflichtfelder aus.");
            return;
        }

        if (formMode === 'create') {
            onCreateFestival(formData as Omit<Festival, 'id' | 'participants' | 'tasks' | 'rsvpDeadline'>);
        } else if (formMode === 'edit') {
            onUpdateFestival(formData as Festival);
        }
        handleCancelForm();
    };
    
    const handleFormInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value } = e.target;
        setFormData(prev => prev ? { ...prev, [name]: name === 'numberOfSaunas' ? parseInt(value, 10) : value } : null);
    };
    
    const handleGenerateTimes = () => {
        const { start, end, interval } = timeGenData;
        if (!start || !end) return;

        const times: string[] = [];
        let currentTime = new Date(`1970-01-01T${start}:00`);
        const endTime = new Date(`1970-01-01T${end}:00`);
        const intervalMinutes = parseInt(interval, 10);

        while (currentTime <= endTime) {
            times.push(currentTime.toTimeString().slice(0, 5));
            currentTime.setMinutes(currentTime.getMinutes() + intervalMinutes);
        }
        
        setFormData(prev => prev ? { ...prev, aufgussTimes: times } : null);
    };
    
    const handleManualTimeChange = (index: number, value: string) => {
        if (!formData || !formData.aufgussTimes) return;
        const newTimes = [...formData.aufgussTimes];
        newTimes[index] = value;
        setFormData(prev => ({ ...prev, aufgussTimes: newTimes }));
    };

    const addManualTime = () => {
        if (!formData) return;
        const newTimes = [...(formData.aufgussTimes || []), '12:00'];
        setFormData(prev => ({ ...prev, aufgussTimes: newTimes }));
    };
    
    const removeManualTime = (index: number) => {
        if (!formData || !formData.aufgussTimes) return;
        const newTimes = formData.aufgussTimes.filter((_, i) => i !== index);
        setFormData(prev => ({ ...prev, aufgussTimes: newTimes }));
    };
    
    const FestivalForm = () => {
        if (!formData) return null;
        return (
            <div className="card festival-form-container">
                 <h3>{formMode === 'create' ? 'Neues Saunafest erstellen' : 'Festival bearbeiten'}</h3>
                 <div className="form-group">
                    <label>Name</label>
                    <input type="text" name="name" value={formData.name || ''} onChange={handleFormInputChange} />
                </div>
                 <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                    <div className="form-group"> <label>Startdatum</label> <input type="date" name="startDate" value={formData.startDate || ''} onChange={handleFormInputChange} /> </div>
                    <div className="form-group"> <label>Enddatum</label> <input type="date" name="endDate" value={formData.endDate || ''} onChange={handleFormInputChange} /> </div>
                </div>
                 <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                    <div className="form-group">
                        <label>Standort</label>
                        <select name="location" value={formData.location} onChange={handleFormInputChange}>
                            {SAUNA_LOCATIONS.map(loc => <option key={loc} value={loc}>{loc}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Anzahl Saunen</label>
                        <select name="numberOfSaunas" value={formData.numberOfSaunas} onChange={handleFormInputChange}>
                            <option value={1}>1</option> <option value={2}>2</option> <option value={3}>3</option>
                        </select>
                    </div>
                </div>
                
                 <h4 style={{marginTop: '2rem'}}>Aufgusszeiten</h4>
                 <div className="time-generator">
                     <div className="form-group">
                         <label>Start</label>
                         <input type="time" value={timeGenData.start} onChange={e => setTimeGenData({...timeGenData, start: e.target.value})}/>
                     </div>
                     <div className="form-group">
                         <label>Ende</label>
                         <input type="time" value={timeGenData.end} onChange={e => setTimeGenData({...timeGenData, end: e.target.value})}/>
                     </div>
                     <div className="form-group">
                         <label>Intervall</label>
                         <select value={timeGenData.interval} onChange={e => setTimeGenData({...timeGenData, interval: e.target.value})}>
                            <option value="60">Volle Stunde</option>
                            <option value="30">Halbe Stunde</option>
                         </select>
                     </div>
                     <button type="button" onClick={handleGenerateTimes}>Zeiten generieren</button>
                 </div>
                 
                 <div className="editable-list scrollable" style={{maxHeight: '200px'}}>
                    {(formData.aufgussTimes || []).map((time, index) => (
                        <div key={index} className="editable-list-item">
                            <input type="time" value={time} onChange={e => handleManualTimeChange(index, e.target.value)} className="editable-list-item-content" />
                            <div className="editable-list-item-actions">
                                <button onClick={() => removeManualTime(index)} title="Zeit entfernen">
                                    <span className="material-icons-outlined">delete</span>
                                </button>
                            </div>
                        </div>
                    ))}
                    {(formData.aufgussTimes?.length ?? 0) === 0 && <p className="info-message" style={{margin: '1rem'}}>Keine Zeiten. Bitte generieren oder manuell hinzufügen.</p>}
                 </div>

                 <div className="festival-form-actions">
                    <button type="button" className="add-option-btn" onClick={addManualTime}>+ Zeit hinzufügen</button>
                    <div style={{ flexGrow: 1 }}></div>
                    <button type="button" className="cancel-btn" onClick={handleCancelForm}>Abbrechen</button>
                    <button type="button" className="save-btn" onClick={handleSaveForm}>{formMode === 'create' ? 'Erstellen' : 'Speichern'}</button>
                </div>
            </div>
        );
    };

    if (formMode === 'create') {
        return (
            <div className="container">
                <FestivalForm />
            </div>
        )
    }

    if (!selectedFestival) {
        return (
             <div className="container">
                <div className="festival-header">
                    <h2>Planung</h2>
                    {canCreateFestivals && <button className="admin-btn" onClick={handleOpenCreateForm}>+ Neues Fest anlegen</button>}
                </div>
                 <p className="info-message">Kein Festival ausgewählt oder vorhanden. Bitte lege ein neues an.</p>
             </div>
        )
    }
    
    const isDeadlinePassed = new Date() > new Date(selectedFestival.rsvpDeadline);
    const isFestivalOver = new Date() > new Date(selectedFestival.endDate);
    const attendingUsers = (selectedFestival.participants ?? []).filter(p => p.status === 'attending').map(p => users.find(u => u.id === p.userId)).filter(Boolean) as User[];


    const renderMemberView = () => {
        if (!myParticipation) return <p className="info-message">Fehler: Deine Teilnahme-Daten konnten nicht geladen werden.</p>
        
        const canLogHours = isFestivalOver && myParticipation.status === 'attending' && !myParticipation.hoursLogged;

        return (
            <>
                {!isDeadlinePassed && myParticipation.status === 'pending' && (
                    <div className="card">
                        <h3>Nimmst du teil?</h3>
                        <p>Bitte gib eine Rückmeldung bis zum {new Date(selectedFestival.rsvpDeadline).toLocaleString('de-DE')}.</p>
                        <div className="rsvp-actions">
                            <button className="accept-btn" onClick={() => handleRsvp('attending')}>Teilnehmen</button>
                            <button className="decline-btn" onClick={() => handleRsvp('not_attending')}>Absagen</button>
                        </div>
                    </div>
                )}
                
                {myParticipation.status !== 'pending' && (
                    <p className="info-message" style={{borderColor: myParticipation.status === 'attending' ? 'var(--success-color)' : 'var(--error-color)'}}>
                        Deine Rückmeldung: <strong>{myParticipation.status === 'attending' ? 'Zusage' : 'Absage'}</strong>.
                    </p>
                )}

                {!isDeadlinePassed && myParticipation.status === 'attending' && (
                    <div className="card">
                        <h3>Verfügbarkeit für Aufgüsse (Uhrzeiten)</h3>
                        <p>An welchen Zeitpunkten wärst du generell verfügbar? (Dies ist unabhängig von deinen festen Angeboten)</p>
                        <div className="availability-grid">
                            {(selectedFestival.aufgussTimes ?? []).map(time => (
                                <label key={time} className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={(myParticipation.aufgussAvailability ?? []).includes(time)}
                                        onChange={e => handleAvailabilityChange(time, e.target.checked)}
                                    />
                                    {time} Uhr
                                </label>
                            ))}
                        </div>
                    </div>
                )}

                {!isDeadlinePassed && myParticipation.status === 'attending' && (
                    <div className="card">
                        <h3>Meine Aufguss-Angebote</h3>
                        <p>Gib an, wie viele Aufgüsse du während des Festivals machen möchtest und gib ihnen einen Namen.</p>
                        <div className="form-group">
                            <label htmlFor="proposal-count">Anzahl der gewünschten Aufgüsse</label>
                            <input
                                type="number"
                                id="proposal-count"
                                min="0"
                                max="10"
                                value={proposals.length}
                                onChange={e => handleProposalCountChange(parseInt(e.target.value, 10) || 0)}
                            />
                        </div>
                        <div className="proposal-inputs">
                            {proposals.map((proposal, index) => (
                                <div className="form-group" key={proposal.id}>
                                    <label htmlFor={`proposal-name-${index}`}>Name Aufguss #{index + 1}</label>
                                    <input
                                        type="text"
                                        id={`proposal-name-${index}`}
                                        placeholder="z.B. 'Sommernachtstraum'"
                                        value={proposal.name}
                                        onChange={e => handleProposalNameChange(index, e.target.value)}
                                    />
                                </div>
                            ))}
                        </div>
                        <button className="save-btn" onClick={handleSaveProposals}>Angebote speichern</button>
                    </div>
                )}

                {canLogHours && (
                     <div className="card">
                        <h3>Arbeitsstunden eintragen</h3>
                        <p>Das Festival ist vorbei. Bitte trage die Anzahl deiner geleisteten Arbeitsstunden ein.</p>
                        <div className="log-hours-form">
                            <input type="number" min="0" value={loggedHours} onChange={e => setLoggedHours(e.target.value)} placeholder="z.B. 8"/>
                            <button className="save-btn" onClick={handleLogHoursSubmit}>Stunden speichern</button>
                        </div>
                    </div>
                )}
                
                <div className="card">
                    <h3>Aufgaben</h3>
                    {(selectedFestival.tasks ?? []).length === 0 ? <p>Keine Aufgaben für dieses Fest.</p> : (
                        <div className="task-list">
                        {(selectedFestival.tasks ?? []).map(task => {
                            const responsibleUser = users.find(u => u.id === task.responsible);
                            const isMyTask = task.responsible === user.id;
                            
                            return (
                                <div key={task.id} className="task-item">
                                    <p className="task-description">{task.description}</p>
                                    <div className="task-status-member">
                                        {responsibleUser ? (
                                            <>
                                                <span>Vergeben an: <strong>{isMyTask ? 'Dich' : responsibleUser.name.split(' ')[0]}</strong></span>
                                                {isMyTask && <button className="release-btn" onClick={() => handleTaskRelease(task.id)}>Abgeben</button>}
                                            </>
                                        ) : (
                                            <>
                                                <span>Frei</span>
                                                <button className="claim-btn" onClick={() => handleTaskClaim(task.id)}>Übernehmen</button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                        </div>
                    )}
                </div>
            </>
        )
    }

    const renderAdminView = () => {
         const participantsByStatus = (selectedFestival.participants ?? []).reduce((acc, p) => {
            acc[p.status].push(users.find(u => u.id === p.userId));
            return acc;
        }, { attending: [], not_attending: [], pending: [] } as Record<'attending' | 'not_attending' | 'pending', (User | undefined)[]>);
        
        const usersWithProposals = attendingUsers
            .map(u => ({
                user: u,
                proposals: (selectedFestival.participants ?? []).find(p => p.userId === u.id)?.aufgussProposals ?? []
            }))
            .filter(item => item.proposals.length > 0);

        return (
            <>
            <div className="post-mode-switcher" style={{maxWidth: '400px', marginBottom: '2rem'}}>
                <button onClick={() => setAdminView('planung')} className={adminView === 'planung' ? 'active' : ''}>Planungsübersicht</button>
                <button onClick={() => setAdminView('aufgaben')} className={adminView === 'aufgaben' ? 'active' : ''}>Aufgaben</button>
            </div>

            {adminView === 'planung' && (
                <>
                    <div className="card">
                        <h3>Teilnehmer-Übersicht</h3>
                        <div className="participant-status-lists">
                             <div><h4>Zusagen ({participantsByStatus.attending.length})</h4><ul>{participantsByStatus.attending.map(u => u && <li key={u.id}>{u.name}</li>)}</ul></div>
                             <div><h4>Absagen ({participantsByStatus.not_attending.length})</h4><ul>{participantsByStatus.not_attending.map(u => u && <li key={u.id}>{u.name}</li>)}</ul></div>
                             <div><h4>Ausstehend ({participantsByStatus.pending.length})</h4><ul>{participantsByStatus.pending.map(u => u && <li key={u.id}>{u.name}</li>)}</ul></div>
                        </div>
                    </div>
                    <div className="card full-width-card">
                        <h3>Aufguss-Angebote der Teilnehmer</h3>
                        <div className="aufguss-proposals-admin-view">
                            {usersWithProposals.length > 0 ? (
                                usersWithProposals.map(({ user, proposals }) => (
                                    <div key={user.id} className="proposal-item">
                                        <div className="proposal-item-header">
                                            {renderAvatar(user.avatarUrl, user.name, 'member-avatar')}
                                            <strong>{user.name}</strong>
                                            <span className="proposal-count-badge">{proposals.length} Angebot{proposals.length !== 1 ? 'e' : ''}</span>
                                        </div>
                                        <ul className="proposal-name-list">
                                            {proposals.map(prop => (
                                                <li key={prop.id}>{prop.name}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ))
                            ) : (
                                <p className="info-message">Bisher wurden keine Aufguss-Angebote gemacht.</p>
                            )}
                        </div>
                    </div>
                    <div className="card full-width-card">
                        <h3>Grafik: Zeitliche Verfügbarkeiten</h3>
                        <div className="availability-planning-grid-wrapper">
                            <table className="availability-planning-grid">
                                <thead>
                                    <tr>
                                        <th>Mitglied</th>
                                        {(selectedFestival.aufgussTimes ?? []).map(time => <th key={time}>{time}</th>)}
                                    </tr>
                                </thead>
                                <tbody>
                                {(selectedFestival.participants ?? []).filter(p=>p.status === 'attending').map(p => {
                                    const participantUser = users.find(u => u.id === p.userId);
                                    if(!participantUser) return null;
                                    return (
                                        <tr key={p.userId}>
                                            <td>{participantUser.name}</td>
                                            {(selectedFestival.aufgussTimes ?? []).map(time => (
                                                <td key={time} className={(p.aufgussAvailability ?? []).includes(time) ? 'available' : ''}>
                                                    {(p.aufgussAvailability ?? []).includes(time) && <span className="material-icons-outlined">check</span>}
                                                </td>
                                            ))}
                                        </tr>
                                    )
                                })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            )}

            {adminView === 'aufgaben' && (
                <>
                <div className="admin-actions">
                    <button className="admin-btn" onClick={() => setTaskModalOpen(true)}>+ Neue Aufgabe erstellen</button>
                </div>
                <div className="card">
                    <h3>Aufgabenverwaltung</h3>
                    {(selectedFestival.tasks ?? []).length === 0 ? <p>Keine Aufgaben für dieses Fest.</p> : (
                         <div className="task-list">
                        {(selectedFestival.tasks ?? []).map(task => {
                            const responsibleUser = users.find(u => u.id === task.responsible);
                            return (
                                <div key={task.id} className="task-item">
                                    <p className="task-description">{task.description}</p>
                                    <div className="task-assignment-admin">
                                        {task.responsible ? (
                                            <>
                                                <span>Vergeben an: <strong>{responsibleUser?.name}</strong></span>
                                                <button className="unassign-btn" onClick={() => handleAdminTaskAssign(task.id, '')}>×</button>
                                            </>
                                        ) : (
                                            <select
                                                value=""
                                                onChange={(e) => handleAdminTaskAssign(task.id, e.target.value)}
                                            >
                                                <option value="">Zuweisen an...</option>
                                                {attendingUsers.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                                            </select>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                        </div>
                    )}
                </div>
                </>
            )}
            </>
        )
    }

    return (
        <div className="container">
            <div className="festival-header">
                <select className="festival-selector" value={selectedFestivalId} onChange={(e) => onSelectFestival(e.target.value)} disabled={festivals.length === 0 || !!formMode}>
                    {festivals.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
                 <div className="festival-header-actions">
                    {canCreateFestivals && (
                        <>
                            <button className="admin-btn" onClick={handleOpenCreateForm} disabled={!!formMode}>+ Neues Fest</button>
                            {festivals.length > 0 && selectedFestival &&
                                <>
                                <button className="admin-btn" onClick={handleOpenEditForm} disabled={!!formMode}>Bearbeiten</button>
                                <button className="delete-btn" onClick={() => onDeleteFestival(selectedFestivalId)} disabled={!!formMode}>Fest löschen</button>
                                </>
                            }
                        </>
                    )}
                </div>
            </div>
            
            {formMode ? <FestivalForm /> : (
                <>
                    <h2>Planung: {selectedFestival.name}</h2>
                    <div className="card" style={{padding: '1rem 2rem', marginBottom: '2rem'}}>
                        <div className="festival-details-grid">
                            <div><strong>Standort:</strong> {selectedFestival.location}</div>
                            <div><strong>Anzahl Saunen:</strong> {selectedFestival.numberOfSaunas}</div>
                            <div><strong>Zeitraum:</strong> {new Date(selectedFestival.startDate).toLocaleDateString('de-DE')} - {new Date(selectedFestival.endDate).toLocaleDateString('de-DE')}</div>
                        </div>
                    </div>
                </>
            )}

            {!formMode && (user.isAdmin ? renderAdminView() : renderMemberView())}


            {taskModalOpen && canCreateFestivals && (
                 <div className="modal-overlay">
                    <div className="modal-content">
                        <h3>Neue Aufgabe erstellen</h3>
                        <div className="form-group">
                            <label htmlFor="task-desc">Aufgabenbeschreibung:</label>
                            <textarea id="task-desc" value={newTaskDesc} onChange={e => setNewTaskDesc(e.target.value)} />
                        </div>
                        <div className="modal-actions">
                            <button className="cancel-btn" onClick={() => setTaskModalOpen(false)}>Abbrechen</button>
                            <button className="save-btn" onClick={handleAddTask}>Speichern</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// --- Social Feed Components ---

// A simple but effective URL parser for embeds
const parseEmbedUrl = (url) => {
    try {
        const urlObj = new URL(url);
        // Spotify
        if (urlObj.hostname.includes('open.spotify.com')) {
            const match = urlObj.pathname.match(/\/(track|playlist|album|artist|episode)\/([a-zA-Z0-9]+)/);
            if (match) return { service: 'spotify', type: match[1], id: match[2] };
        }
        // YouTube
        if (urlObj.hostname.includes('youtube.com') || urlObj.hostname.includes('youtu.be')) {
            const videoId = urlObj.hostname.includes('youtu.be')
                ? urlObj.pathname.slice(1)
                : urlObj.searchParams.get('v');
            if (videoId) return { service: 'youtube', id: videoId };
        }
        // Instagram
        if (urlObj.hostname.includes('instagram.com') && (urlObj.pathname.startsWith('/p/') || urlObj.pathname.startsWith('/reel/'))) {
            return { service: 'instagram', url: url.split("?")[0] };
        }
        // TikTok
        if (urlObj.hostname.includes('tiktok.com')) {
             if(urlObj.pathname.includes('/video/')) {
                return { service: 'tiktok', url: url.split("?")[0] };
             }
        }
    } catch (e) {
        // Not a valid URL
        return null;
    }
    return null;
};

// Renders the correct embed based on the URL
const EmbedRenderer = ({ url }) => {
    const embedData = useMemo(() => parseEmbedUrl(url), [url]);
    const embedRef = useRef<HTMLDivElement>(null);
    
    // This effect is crucial for Instagram and TikTok embeds to render
    useEffect(() => {
        if (embedData?.service === 'instagram' && typeof window.instgrm?.Embeds?.process === 'function') {
            window.instgrm.Embeds.process();
        }
        if (embedData?.service === 'tiktok' && typeof window.tiktok?.embed?.render === 'function') {
             // TikTok can be finicky. Sometimes it needs a re-render trigger.
             // A timeout ensures the DOM element is there.
             setTimeout(() => {
                if (embedRef.current?.querySelector('.tiktok-embed')) {
                    window.tiktok.embed.render();
                }
             }, 100);
        }
    }, [embedData]);

    if (!embedData) {
        return <div className="info-message error-message">Link konnte nicht verarbeitet werden. Stelle sicher, dass es ein gültiger Link von YouTube, Spotify, Instagram oder TikTok ist.</div>;
    }

    return (
        <div ref={embedRef}>
            {(() => {
                switch (embedData.service) {
                    case 'youtube':
                        return (
                            <div className="youtube-embed-container">
                                <iframe
                                    src={`https://www.youtube.com/embed/${embedData.id}`}
                                    frameBorder="0"
                                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                    allowFullScreen
                                    title="Eingebettetes YouTube Video"
                                ></iframe>
                            </div>
                        );
                    case 'spotify':
                        return (
                             <iframe
                                className="spotify-embed"
                                src={`https://open.spotify.com/embed/${embedData.type}/${embedData.id}`}
                                width="100%"
                                height={embedData.type === 'track' ? '152' : '380'}
                                frameBorder="0"
                                allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                                loading="lazy"
                            ></iframe>
                        );
                    case 'instagram':
                        return (
                            <blockquote
                                className="instagram-media instagram-embed"
                                data-instgrm-permalink={embedData.url}
                                data-instgrm-version="14"
                            ></blockquote>
                        );
                     case 'tiktok':
                        return (
                            <blockquote
                                className="tiktok-embed"
                                cite={embedData.url}
                                data-video-id={embedData.url.split('video/')[1].split('/')[0]}
                            >
                                <section></section>
                            </blockquote>
                        );
                    default:
                        return <div className="info-message error-message">Dieser Link-Typ wird nicht unterstützt.</div>;
                }
            })()}
        </div>
    );
};

const SocialFeed = ({ currentUser, users, posts, onAddPost, onLikePost, onAddComment, onVote, onDeletePost, onDeleteComment }: { currentUser: User, users: User[], posts: Post[], onAddPost: (post: Omit<Post, 'id' | 'userId' | 'timestamp' | 'likes' | 'comments'>) => void, onLikePost: (postId: number) => void, onAddComment: (postId: number, text: string) => void, onVote: (postId: number, optionIndex: number) => void, onDeletePost: (postId: number) => void, onDeleteComment: (postId: number, commentId: number) => void }) => {
    const [postMode, setPostMode] = useState<'text' | 'poll' | 'image' | 'embed'>('text');
    const [newPostContent, setNewPostContent] = useState('');
    const [pollQuestion, setPollQuestion] = useState('');
    const [pollOptions, setPollOptions] = useState(['', '']);
    const [commentInputs, setCommentInputs] = useState<{[key: number]: string}>({});
    const [imagePreview, setImagePreview] = useState<string | null>(null);
    const [embedUrl, setEmbedUrl] = useState('');
    const [isCompressing, setIsCompressing] = useState(false);

    const fileInputRef = React.useRef<HTMLInputElement>(null);

    const getUser = (userId: number) => users.find(u => u.id === userId);
    
    const canDeletePost = (postUserId: number) => currentUser.isAdmin || currentUser.permissions.includes('delete_content') || currentUser.id === postUserId;
    const canDeleteComment = (commentUserId: number) => currentUser.isAdmin || currentUser.permissions.includes('delete_content') || currentUser.id === commentUserId;

    
    const handlePollOptionChange = (index: number, value: string) => {
        const newOptions = [...pollOptions];
        newOptions[index] = value;
        setPollOptions(newOptions);
    };

    const addPollOption = () => {
        if (pollOptions.length < 10) setPollOptions([...pollOptions, '']);
    };
    const removePollOption = (index: number) => {
        if (pollOptions.length > 2) setPollOptions(pollOptions.filter((_, i) => i !== index));
    };

    const resetInputs = () => {
        setNewPostContent('');
        setPollQuestion('');
        setPollOptions(['', '']);
        setImagePreview(null);
        setEmbedUrl('');
        if(fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };
    
    const handleModeChange = (mode: 'text' | 'poll' | 'image' | 'embed') => {
        resetInputs();
        setPostMode(mode);
    };

    const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setIsCompressing(true);

        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                const MAX_WIDTH = 1024;
                const MAX_HEIGHT = 1024;
                let width = img.width;
                let height = img.height;

                if (width > height) {
                    if (width > MAX_WIDTH) {
                        height *= MAX_WIDTH / width;
                        width = MAX_WIDTH;
                    }
                } else {
                    if (height > MAX_HEIGHT) {
                        width *= MAX_HEIGHT / height;
                        height = MAX_HEIGHT;
                    }
                }
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx?.drawImage(img, 0, 0, width, height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.7); // Compress to 70% quality JPEG
                setImagePreview(dataUrl);
                setIsCompressing(false);
            };
            img.src = e.target?.result as string;
        };
        reader.readAsDataURL(file);
    };

    const handlePostSubmit = () => {
        if (postMode === 'text') {
            if (newPostContent.trim()) {
                onAddPost({ type: 'text', content: newPostContent.trim() });
            }
        } else if (postMode === 'poll') {
            if (pollQuestion.trim() && pollOptions.every(opt => opt.trim())) {
                onAddPost({
                    type: 'poll',
                    content: pollQuestion.trim(),
                    pollData: {
                        question: pollQuestion.trim(),
                        options: pollOptions.map(opt => ({ text: opt.trim(), votes: [] }))
                    }
                });
            }
        } else if (postMode === 'image') {
            if (imagePreview) {
                onAddPost({
                    type: 'image',
                    content: newPostContent.trim(), // caption
                    imageUrl: imagePreview,
                });
            }
        } else if (postMode === 'embed') {
             if (embedUrl.trim() && parseEmbedUrl(embedUrl.trim())) {
                onAddPost({
                    type: 'embed',
                    content: newPostContent.trim(), // caption
                    embedUrl: embedUrl.trim()
                });
            } else {
                alert("Bitte gib eine gültige URL von YouTube, Spotify, Instagram oder TikTok ein.")
            }
        }
        resetInputs();
    };
    
    const handleCommentChange = (postId: number, text: string) => {
        setCommentInputs({...commentInputs, [postId]: text});
    }

    const handleCommentSubmit = (postId: number) => {
        const text = commentInputs[postId];
        if(text && text.trim()){
            onAddComment(postId, text.trim());
            setCommentInputs({...commentInputs, [postId]: ''});
        }
    }

    return (
        <div className="container social-feed">
            <h2>Social Feed</h2>
            <div className="card new-post-card">
                <div className="post-mode-switcher">
                    <button onClick={() => handleModeChange('text')} className={postMode === 'text' ? 'active' : ''}>Beitrag</button>
                    <button onClick={() => handleModeChange('poll')} className={postMode === 'poll' ? 'active' : ''}>Umfrage</button>
                    <button onClick={() => handleModeChange('image')} className={postMode === 'image' ? 'active' : ''}>Bild</button>
                    <button onClick={() => handleModeChange('embed')} className={postMode === 'embed' ? 'active' : ''}>Link</button>
                </div>
                {postMode === 'text' && (
                    <textarea
                        placeholder={`Was gibt's Neues, ${currentUser.name.split(' ')[0]}?`}
                        value={newPostContent}
                        onChange={e => setNewPostContent(e.target.value)}
                    />
                )}
                {postMode === 'poll' && (
                    <div className="poll-creator">
                        <input type="text" placeholder="Deine Frage..." value={pollQuestion} onChange={e => setPollQuestion(e.target.value)} />
                        <div className="poll-options">
                            {pollOptions.map((opt, index) => (
                                <div key={index} className="poll-option-input">
                                    <input type="text" placeholder={`Option ${index + 1}`} value={opt} onChange={e => handlePollOptionChange(index, e.target.value)} />
                                    {pollOptions.length > 2 && <button onClick={() => removePollOption(index)}>&times;</button>}
                                </div>
                            ))}
                        </div>
                        {pollOptions.length < 10 && <button className="add-option-btn" onClick={addPollOption}>+ Option hinzufügen</button>}
                    </div>
                )}
                 {postMode === 'image' && (
                    <div className="image-uploader">
                        <textarea
                            placeholder="Bildbeschreibung (optional)..."
                            value={newPostContent}
                            onChange={e => setNewPostContent(e.target.value)}
                        />
                        {imagePreview && (
                            <div className="image-preview-container">
                                <img src={imagePreview} alt="Vorschau" className="image-preview" />
                                <button className="remove-image-btn" onClick={() => {setImagePreview(null); if(fileInputRef.current) fileInputRef.current.value = ''; }}>&times;</button>
                            </div>
                        )}
                        <input type="file" accept="image/*" ref={fileInputRef} onChange={handleImageChange} style={{display: 'none'}} id="image-upload-input"/>
                        <label htmlFor="image-upload-input" className={`image-upload-label ${isCompressing ? 'disabled' : ''}`}>
                            <span className="material-icons-outlined">add_photo_alternate</span>
                            {isCompressing ? 'Bild wird verarbeitet...' : (imagePreview ? 'Anderes Bild wählen' : 'Bild auswählen')}
                        </label>
                    </div>
                )}
                 {postMode === 'embed' && (
                    <div className="embed-uploader">
                        <input type="text" placeholder="Link von YouTube, Spotify, Instagram, TikTok..." value={embedUrl} onChange={e => setEmbedUrl(e.target.value)} />
                        <textarea
                            placeholder="Beschreibung (optional)..."
                            value={newPostContent}
                            onChange={e => setNewPostContent(e.target.value)}
                        />
                    </div>
                )}
                <button onClick={handlePostSubmit} disabled={isCompressing}>Posten</button>
            </div>

            {posts.map(post => {
                const postUser = getUser(post.userId);
                if (!postUser) return null;
                const totalVotes = post.type === 'poll' ? post.pollData?.options.reduce((sum, opt) => sum + opt.votes.length, 0) || 0 : 0;
                const userHasVoted = post.type === 'poll' ? post.pollData?.options.some(opt => opt.votes.includes(currentUser.id)) : false;

                return (
                    <div className="card" key={post.id}>
                        <div className="post-header">
                            {renderAvatar(postUser.avatarUrl, postUser.name, 'post-avatar')}
                            <div>
                                <strong>{postUser.name}</strong>
                                <span className="timestamp">{post.timestamp}</span>
                            </div>
                             {canDeletePost(post.userId) && (
                                <button className="delete-post-btn" title="Beitrag löschen" onClick={() => onDeletePost(post.id)}>
                                    <span className="material-icons-outlined">delete_forever</span>
                                </button>
                            )}
                        </div>
                        
                        {post.content && <p className="post-content">{post.content}</p>}

                        {post.type === 'image' && post.imageUrl && (
                             <img src={post.imageUrl} alt={post.content || 'Gepostetes Bild'} className="post-image" />
                        )}

                        {post.type === 'embed' && post.embedUrl && (
                             <div className="embed-container">
                                <EmbedRenderer url={post.embedUrl} />
                            </div>
                        )}
                        
                        {post.type === 'poll' && post.pollData && (
                            <div className="poll-container">
                                {post.pollData.options.map((option, index) => {
                                    const votesForOption = option.votes.length;
                                    const percentage = totalVotes > 0 ? (votesForOption / totalVotes) * 100 : 0;
                                    const userVotedForThis = option.votes.includes(currentUser.id);

                                    return (
                                        <div key={index} className={`poll-option ${userHasVoted ? 'voted' : ''}`} onClick={() => !userHasVoted && onVote(post.id, index)}>
                                            <div className="poll-option-result" style={{ width: `${userHasVoted ? percentage : 0}%` }}></div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', position: 'relative', zIndex: 2 }}>
                                                <span className="poll-option-text">{option.text}</span>
                                                {userHasVoted && (
                                                    <span className="poll-option-votes">
                                                        {userVotedForThis && <span className="material-icons-outlined self-vote-check">check_circle</span>}
                                                        {votesForOption} Stimme(n) ({Math.round(percentage)}%)
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}

                        <div className="post-actions">
                             <button onClick={() => onLikePost(post.id)} className={post.likes.includes(currentUser.id) ? 'liked' : ''}>
                                <span className="material-icons-outlined">thumb_up</span>
                                 {post.likes.length > 0 ? post.likes.length : ''}
                            </button>
                            <button>
                                <span className="material-icons-outlined">comment</span>
                                 {post.comments.length > 0 ? post.comments.length : ''}
                            </button>
                        </div>

                        <div className="post-comments">
                            {post.comments.map(comment => {
                                const commentUser = getUser(comment.userId);
                                return (
                                    <div className="comment" key={comment.id}>
                                        <div><strong>{commentUser?.name.split(' ')[0]}:</strong> {comment.text}</div>
                                        {canDeleteComment(comment.userId) && (
                                            <button className="delete-comment-btn" title="Kommentar löschen" onClick={() => onDeleteComment(post.id, comment.id)}>
                                                <span className="material-icons-outlined">delete</span>
                                            </button>
                                        )}
                                    </div>
                                )
                            })}
                            <div className="comment-input-container">
                                <input 
                                    type="text" 
                                    placeholder="Dein Kommentar..." 
                                    value={commentInputs[post.id] || ''} 
                                    onChange={e => handleCommentChange(post.id, e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleCommentSubmit(post.id) }}
                                />
                                <button onClick={() => handleCommentSubmit(post.id)}>Senden</button>
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    );
};

const PermissionEditModal = ({ isOpen, onClose, user, onSave }) => {
    const [selectedPermissions, setSelectedPermissions] = useState<Permission[]>(user?.permissions || []);

    useEffect(() => {
        if (user) {
            setSelectedPermissions(user.permissions);
        }
    }, [user]);

    if (!isOpen || !user) return null;

    const handleCheckboxChange = (permission: Permission, isChecked: boolean) => {
        setSelectedPermissions(prev =>
            isChecked ? [...prev, permission] : prev.filter(p => p !== permission)
        );
    };

    const handleSave = () => {
        onSave(user.id, selectedPermissions);
        onClose();
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <h3>Rechte für {user.name} bearbeiten</h3>
                <div className="form-group checkbox-group">
                    {AVAILABLE_PERMISSIONS.map(p => (
                        <label key={p.id} className="checkbox-label">
                            <input
                                type="checkbox"
                                checked={selectedPermissions.includes(p.id)}
                                onChange={e => handleCheckboxChange(p.id, e.target.checked)}
                            />
                            {p.description}
                        </label>
                    ))}
                </div>
                <div className="modal-actions">
                    <button className="cancel-btn" onClick={onClose}>Abbrechen</button>
                    <button className="save-btn" onClick={handleSave}>Speichern</button>
                </div>
            </div>
        </div>
    );
};

const AwardEditModal = ({ isOpen, onClose, user, awards, allAwards, onSave, onCreateAward }) => {
    const [selectedAwards, setSelectedAwards] = useState<string[]>(user?.awards || []);
    const [showCreate, setShowCreate] = useState(false);
    const [newAward, setNewAward] = useState({ name: '', icon: 'workspace_premium', color: '#FFD700'});

    useEffect(() => {
        if (user) {
            setSelectedAwards(user.awards);
        }
    }, [user]);

    if (!isOpen || !user) return null;

    const handleCheckboxChange = (awardId: string, isChecked: boolean) => {
        setSelectedAwards(prev =>
            isChecked ? [...prev, awardId] : prev.filter(id => id !== awardId)
        );
    };

    const handleSave = () => {
        onSave(user.id, selectedAwards);
        onClose();
    };
    
    const handleCreate = () => {
        if (newAward.name.trim() && newAward.icon.trim()) {
            onCreateAward({ ...newAward, id: `custom_${Date.now()}`});
            setNewAward({ name: '', icon: 'workspace_premium', color: '#FFD700'});
            setShowCreate(false);
        }
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <h3>Auszeichnungen für {user.name}</h3>
                <div className="form-group checkbox-group scrollable">
                    {allAwards.map(award => (
                        <label key={award.id} className="checkbox-label">
                            <input
                                type="checkbox"
                                checked={selectedAwards.includes(award.id)}
                                onChange={e => handleCheckboxChange(award.id, e.target.checked)}
                            />
                            <span className="material-icons-outlined" style={{color: award.color}}>{award.icon}</span>
                            {award.name}
                        </label>
                    ))}
                </div>
                
                 {showCreate ? (
                    <div className="card" style={{marginTop: '1rem'}}>
                        <h4>Neue Auszeichnung erstellen</h4>
                        <div className="form-group">
                            <label>Name</label>
                            <input type="text" value={newAward.name} onChange={e => setNewAward({...newAward, name: e.target.value})} />
                        </div>
                        <div className="form-group">
                            <label>Icon (<a href="https://fonts.google.com/icons" target="_blank">Material Icon Name</a>)</label>
                            <input type="text" value={newAward.icon} onChange={e => setNewAward({...newAward, icon: e.target.value})} />
                        </div>
                         <div className="form-group">
                            <label>Farbe</label>
                            <input type="color" value={newAward.color} onChange={e => setNewAward({...newAward, color: e.target.value})} />
                        </div>
                        <button className="save-btn" onClick={handleCreate}>Erstellen</button>
                    </div>
                ) : (
                    <button className="admin-btn" style={{marginTop: '1rem'}} onClick={() => setShowCreate(true)}>+ Neue Auszeichnung erstellen</button>
                )}
                
                <div className="modal-actions">
                    <button className="cancel-btn" onClick={onClose}>Abbrechen</button>
                    <button className="save-btn" onClick={handleSave}>Speichern</button>
                </div>
            </div>
        </div>
    );
};

const QualificationAssignmentModal = ({
    isOpen,
    onClose,
    user,
    allQuals,
    availableQuals,
    onSave,
    onAddQual,
    onDeleteQual,
}) => {
    const [selectedQuals, setSelectedQuals] = useState<string[]>(user?.qualifications || []);
    const [isManaging, setIsManaging] = useState(false);
    const [newQual, setNewQual] = useState('');

    useEffect(() => {
        if (user) {
            setSelectedQuals(user.qualifications);
            setIsManaging(false); // Reset view on user change
        }
    }, [user]);

    if (!isOpen || !user) return null;

    const handleCheckboxChange = (qual: string, isChecked: boolean) => {
        setSelectedQuals(prev =>
            isChecked ? [...prev, qual] : prev.filter(q => q !== qual)
        );
    };
    
    const handleSave = () => {
        onSave(user.id, selectedQuals);
        onClose();
    };

    const handleAdd = () => {
        if (newQual.trim() && !availableQuals.includes(newQual.trim())) {
            onAddQual(newQual.trim());
            setNewQual('');
        }
    };
    
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                {isManaging ? (
                    <>
                        <h3>
                            Qualifikationen Verwalten
                             <button className="admin-btn" onClick={() => setIsManaging(false)}>Zurück</button>
                        </h3>
                        <div className="editable-list">
                            {availableQuals.map(q => (
                                <div key={q} className="editable-list-item">
                                    <span>{q}</span>
                                    <div className="editable-list-item-actions">
                                        <button onClick={() => onDeleteQual(q)} title="Löschen"><span className="material-icons-outlined">delete</span></button>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="editable-list-form">
                            <input 
                                type="text" 
                                placeholder="Neue Qualifikation..." 
                                value={newQual}
                                onChange={e => setNewQual(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && handleAdd()}
                            />
                            <button className="save-btn" onClick={handleAdd}>Hinzufügen</button>
                        </div>
                    </>
                ) : (
                    <>
                        <h3>
                            Qualifikationen für {user.name}
                            <button className="admin-btn" onClick={() => setIsManaging(true)}>Verwalten</button>
                        </h3>
                        <div className="form-group checkbox-group scrollable">
                            {availableQuals.map(qual => (
                                <label key={qual} className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={selectedQuals.includes(qual)}
                                        onChange={e => handleCheckboxChange(qual, e.target.checked)}
                                    />
                                    {qual}
                                </label>
                            ))}
                        </div>
                    </>
                )}

                <div className="modal-actions">
                    <button className="cancel-btn" onClick={onClose}>Abbrechen</button>
                    {!isManaging && <button className="save-btn" onClick={handleSave}>Speichern</button>}
                </div>
            </div>
        </div>
    );
};


const MembersPage = ({ currentUser, users, onViewProfile, onOpenPermissionsModal, onOpenAwardsModal, onOpenQualsModal, onDeleteUser }) => {
    return (
        <div className="container">
            <h2>Mitgliederverzeichnis</h2>
            <div className="card" style={{padding: 0, overflowX: 'auto'}}>
                 <table className="member-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Haupt-Sauna</th>
                            <th>Aufgüsse</th>
                            {currentUser.isAdmin && <th>Aktionen</th>}
                        </tr>
                    </thead>
                    <tbody>
                        {users.filter(u => u.isAdmin || u.showInMemberList).map(user => (
                            <tr key={user.id} className="clickable" onClick={() => onViewProfile(user.id)}>
                                <td>
                                    <div className="member-name-cell">
                                        {renderAvatar(user.avatarUrl, user.name, 'member-avatar')}
                                        <div className="member-details">
                                            <span className="member-name">
                                                {user.name}
                                                {user.isAdmin && <span className="admin-badge">Admin</span>}
                                            </span>
                                            {user.motto && <span className="member-motto">"{user.motto}"</span>}
                                        </div>
                                    </div>
                                </td>
                                <td>{user.primarySauna}</td>
                                <td>{user.aufgussCount}</td>
                                {currentUser.isAdmin && (
                                    <td onClick={e => e.stopPropagation()}>
                                        <div className="actions-cell">
                                            <button className="admin-btn" onClick={() => onOpenPermissionsModal(user)}>Rechte</button>
                                            <button className="admin-btn" onClick={() => onOpenAwardsModal(user)}>Auszeichnungen</button>
                                            <button className="delete-btn" onClick={() => onDeleteUser(user.id)}>Löschen</button>
                                            <button className="admin-btn quals-btn" onClick={() => onOpenQualsModal(user)}>Qualifikationen</button>
                                        </div>
                                    </td>
                                )}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const BerichtePage = ({ users, aufguesse }) => {
     const [selectedMonth, setSelectedMonth] = useState(new Date().toISOString().slice(0, 7));

    const monthlyData = useMemo(() => {
        const [year, month] = selectedMonth.split('-').map(Number);
        
        const aufguesseInMonth = aufguesse.filter(a => {
            const aDate = new Date(a.date);
            return aDate.getFullYear() === year && (aDate.getMonth() + 1) === month;
        });
        
        const report = users.map(user => {
            const userAufguesse = aufguesseInMonth.filter(a => a.aufgussmeisterId === user.id);
            return {
                user,
                count: userAufguesse.length,
                types: userAufguesse.reduce((acc, a) => {
                    if (a.type) acc[a.type] = (acc[a.type] || 0) + 1;
                    return acc;
                }, {}),
            };
        }).filter(r => r.count > 0).sort((a,b) => b.count - a.count);

        return report;
    }, [users, aufguesse, selectedMonth]);

    return (
        <div className="container reports-container">
            <h2>Berichte</h2>
            <div className="card report-section">
                <div className="report-header">
                    <h3>Monatliche Aufguss-Statistik</h3>
                    <input type="month" value={selectedMonth} onChange={e => setSelectedMonth(e.target.value)} />
                </div>
                <div style={{overflowX: 'auto'}}>
                     <table className="member-table">
                        <thead>
                            <tr>
                                <th>Aufgussmeister</th>
                                <th>Anzahl</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody>
                            {monthlyData.length > 0 ? monthlyData.map(({ user, count, types }) => (
                                <tr key={user.id}>
                                    <td>{user.name}</td>
                                    <td>{count}</td>
                                    <td>
                                        {Object.entries(types).map(([type, num]) => `${type} (${num})`).join(', ')}
                                    </td>
                                </tr>
                            )) : (
                                <tr>
                                    <td colSpan={3} style={{textAlign: 'center'}}>Keine Daten für diesen Monat.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};


// --- Main App Component ---
const App = () => {
    // State Initialization
    const [appStage, setAppStage] = useState<AppStage>('loading');
    const [view, setView] = useState<View>('dashboard');
    const [users, setUsers] = useState<User[]>([]);
    const [posts, setPosts] = useState<Post[]>([]);
    const [festivals, setFestivals] = useState<Festival[]>([]);
    const [aufguesse, setAufguesse] = useState<Aufguss[]>([]);
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [registrationCode, setRegistrationCode] = useState('');
    const [selectedFestivalId, setSelectedFestivalId] = useState<string>('');
    const [awards, setAwards] = useState<Award[]>([]);
    const [aufgussTypes, setAufgussTypes] = useState<string[]>([]);
    const [availableQuals, setAvailableQuals] = useState<string[]>([]);
    const [persistedBackgrounds, setPersistedBackgrounds] = useState<Record<string, string>>({});
    
    const [viewedUserId, setViewedUserId] = useState<number | null>(null);

    // Modal States
    const [isPermissionsModalOpen, setIsPermissionsModalOpen] = useState(false);
    const [isAwardModalOpen, setIsAwardModalOpen] = useState(false);
    const [isQualsModalOpen, setIsQualsModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);
    
    // Initial data loading effect
    useEffect(() => {
        const loadData = async () => {
            try {
                const data = await apiClient.loadAllData();
                setUsers(data.users);
                setPosts(data.posts);
                setAufguesse(data.aufguesse);
                setAwards(data.awards);
                setAufgussTypes(data.aufgussTypes);
                setAvailableQuals(data.availableQuals);
                setRegistrationCode(data.registrationCode);
                setPersistedBackgrounds(data.persistedBackgrounds);

                // Festival state needs careful handling to ensure data integrity
                setFestivals(data.festivals);
                if (data.festivals.length > 0) {
                    const savedId = data.selectedFestivalId;
                    if (savedId && data.festivals.some(f => f.id === savedId)) {
                        setSelectedFestivalId(savedId);
                    } else {
                        setSelectedFestivalId(data.festivals[0].id);
                    }
                } else {
                    setSelectedFestivalId('');
                }
            } catch (error) {
                console.error("Failed to load initial data", error);
                // Optionally show an error message to the user
            } finally {
                // Check for a logged-in user could go here in a real app
                setAppStage('login');
            }
        };

        loadData();
    }, []);
    
    const handleLogout = useCallback(() => {
        setCurrentUser(null);
        setAppStage('login');
    }, []);
    
    const changeView = useCallback((newView: View, targetUserId: number | null = null) => {
        const container = document.querySelector('.view-container');
        container?.classList.add('fading');
        
        if (newView === 'profile' && targetUserId === currentUser?.id) {
            setViewedUserId(null);
        } else {
            setViewedUserId(targetUserId);
        }

        setTimeout(() => {
            setView(newView);
            container?.classList.remove('fading');
        }, 300);
    }, [currentUser?.id]);
    
    const memoizedChangeView = useCallback(changeView, [changeView]);
    const memoizedOnLogout = useCallback(handleLogout, [handleLogout]);


    // --- Authentication & Registration Handlers ---
    const handleLogin = (username: string, password: string) => {
        const user = users.find(u => u.username === username); // In a real app, check hashed password
        if (user) {
            setCurrentUser(user);
            setAppStage('loggedIn');
        } else {
            alert('Falscher Benutzername oder Passwort.');
        }
    };

    const handleGoToRegister = () => setAppStage('register');
    const handleBackToLogin = () => setAppStage('login');

    const handleCodeSubmit = () => setAppStage('profile_setup');
    
    const handleCompleteRegistration = async (newUserData: Omit<User, 'id' | 'avatarUrl' | 'qualifications' | 'awards' | 'aufgussCount' | 'workHours' | 'isAdmin' | 'status' | 'shortNoticeCancellations' | 'showInMemberList' | 'permissions' | 'lastProfileUpdate' | 'lastAufgussShareTimestamp'>) => {
        const newUser: User = {
            id: Date.now(),
            ...newUserData,
            avatarUrl: EMOJI_AVATARS[Math.floor(Math.random() * EMOJI_AVATARS.length)],
            qualifications: [],
            awards: [],
            aufgussCount: 0,
            workHours: 0,
            isAdmin: false,
            permissions: [],
            status: 'active',
            shortNoticeCancellations: 0,
            showInMemberList: true,
            lastProfileUpdate: Date.now(),
            lastAufgussShareTimestamp: 0,
        };

        const newFestivals = festivals.map(festival => {
            if (festival.participants.some(p => p.userId === newUser.id)) {
                return festival;
            }
            const newParticipant: FestivalParticipant = {
                userId: newUser.id,
                status: 'pending',
                aufgussAvailability: [],
                workHours: 0,
                hoursLogged: false,
                aufgussProposals: [],
            };
            return {
                ...festival,
                participants: [...festival.participants, newParticipant]
            };
        });
        setFestivals(newFestivals);
        await apiClient.saveFestivals(newFestivals);
        
        const newUsers = [...users, newUser];
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);

        setCurrentUser(newUser);
        setAppStage('loggedIn');
        setView('dashboard');
    };

    // --- User Management Handlers ---
    const handleUpdateUser = async (updatedData: Partial<User>) => {
        const targetUserId = viewedUserId ?? currentUser!.id;
        
        const newUsers = users.map(u => 
            u.id === targetUserId ? { ...u, ...updatedData } : u
        );
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);

        if (currentUser && currentUser.id === targetUserId) {
            setCurrentUser(prev => prev ? { ...prev, ...updatedData } : null);
        }
    };
    
    const handleDeleteUser = async (userId: number) => {
        if (window.confirm('Bist du sicher, dass du dieses Mitglied endgültig löschen möchtest?')) {
            const newUsers = users.filter(u => u.id !== userId);
            setUsers(newUsers);
            await apiClient.saveUsers(newUsers);
        }
    };

    const handleBackToList = () => {
        changeView('mitglieder');
    };
    
    // --- Modals Handlers ---
    const handleOpenPermissionsModal = (user: User) => {
        setEditingUser(user);
        setIsPermissionsModalOpen(true);
    };

    const handleSavePermissions = async (userId: number, permissions: Permission[]) => {
        const newUsers = users.map(u => u.id === userId ? { ...u, permissions } : u);
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);
    };
    
    const handleOpenAwardsModal = (user: User) => {
        setEditingUser(user);
        setIsAwardModalOpen(true);
    };

    const handleSaveAwards = async (userId: number, awardIds: string[]) => {
        const newUsers = users.map(u => u.id === userId ? { ...u, awards: awardIds } : u);
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);
    };
    
    const handleCreateAward = async (newAward: Award) => {
        const newAwards = [...awards, newAward];
        setAwards(newAwards);
        await apiClient.saveAwards(newAwards);
    };
    
    const handleOpenQualsModal = (user: User) => {
        setEditingUser(user);
        setIsQualsModalOpen(true);
    };

    const handleSaveQuals = async (userId: number, quals: string[]) => {
        const newUsers = users.map(u => u.id === userId ? { ...u, qualifications: quals } : u);
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);
    };

    const handleAddQual = async (qual: string) => {
        const newQuals = [...availableQuals, qual];
        setAvailableQuals(newQuals);
        await apiClient.saveAvailableQuals(newQuals);
    };

    const handleDeleteQual = async (qualToDelete: string) => {
        const newAvailableQuals = availableQuals.filter(q => q !== qualToDelete);
        setAvailableQuals(newAvailableQuals);
        await apiClient.saveAvailableQuals(newAvailableQuals);

        const newUsers = users.map(u => ({
            ...u,
            qualifications: u.qualifications.filter(q => q !== qualToDelete)
        }));
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);
    };

    // --- Social Feed Handlers ---
    const handleAddPost = async (postData: Omit<Post, 'id' | 'userId' | 'timestamp' | 'likes' | 'comments'>) => {
        const newPost: Post = {
            ...postData,
            id: Date.now(),
            userId: currentUser!.id,
            timestamp: `gerade eben`,
            likes: [],
            comments: []
        };
        const newPosts = [newPost, ...posts];
        setPosts(newPosts);
        await apiClient.savePosts(newPosts);
    };

    const handleLikePost = async (postId: number) => {
        const newPosts = posts.map(p => {
            if (p.id === postId) {
                const liked = p.likes.includes(currentUser!.id);
                const newLikes = liked
                    ? p.likes.filter(id => id !== currentUser!.id)
                    : [...p.likes, currentUser!.id];
                return { ...p, likes: newLikes };
            }
            return p;
        });
        setPosts(newPosts);
        await apiClient.savePosts(newPosts);
    };
    
    const handleAddComment = async (postId: number, text: string) => {
         const newPosts = posts.map(p => {
            if (p.id === postId) {
                const newComment: Comment = {
                    id: Date.now(),
                    userId: currentUser!.id,
                    text
                };
                return { ...p, comments: [...p.comments, newComment] };
            }
            return p;
        });
        setPosts(newPosts);
        await apiClient.savePosts(newPosts);
    };
    
    const onVote = async (postId: number, optionIndex: number) => {
        const newPosts = posts.map(p => {
            if (p.id === postId && p.type === 'poll' && p.pollData) {
                if (p.pollData.options.some(opt => opt.votes.includes(currentUser!.id))) {
                    return p;
                }
                const newOptions = p.pollData.options.map((opt, index) => {
                    if (index === optionIndex) {
                        return { ...opt, votes: [...opt.votes, currentUser!.id] };
                    }
                    return opt;
                });
                return { ...p, pollData: { ...p.pollData, options: newOptions } };
            }
            return p;
        });
        setPosts(newPosts);
        await apiClient.savePosts(newPosts);
    };
    
    const onDeletePost = async (postId: number) => {
        if(window.confirm('Bist du sicher, dass du diesen Beitrag löschen möchtest?')) {
            const newPosts = posts.filter(p => p.id !== postId);
            setPosts(newPosts);
            await apiClient.savePosts(newPosts);
        }
    };
    
    const onDeleteComment = async (postId: number, commentId: number) => {
        const newPosts = posts.map(p => {
            if (p.id === postId) {
                return {...p, comments: p.comments.filter(c => c.id !== commentId)};
            }
            return p;
        });
        setPosts(newPosts);
        await apiClient.savePosts(newPosts);
    };
    
    // --- Aufguss Handlers ---
    const handleClaimAufguss = async (aufgussId: string, type: string) => {
        const newAufguesse = aufguesse.map(a =>
            a.id === aufgussId
                ? { ...a, aufgussmeisterId: currentUser!.id, aufgussmeisterName: currentUser!.name, type }
                : a
        );
        setAufguesse(newAufguesse);
        await apiClient.saveAufguesse(newAufguesse);
        
        const newUsers = users.map(u => u.id === currentUser!.id ? {...u, aufgussCount: u.aufgussCount + 1} : u);
        setUsers(newUsers);
        setCurrentUser(newUsers.find(u => u.id === currentUser!.id) || null);
        await apiClient.saveUsers(newUsers);
    };

    const handleCancelAufguss = async (aufgussId: string) => {
        const aufgussToCancel = aufguesse.find(a => a.id === aufgussId);
        if (!aufgussToCancel || !aufgussToCancel.aufgussmeisterId) return;

        if (window.confirm('Bist du sicher, dass du diesen Aufguss stornieren möchtest?')) {
            const aufgussDateTime = new Date(`${aufgussToCancel.date}T${aufgussToCancel.time}`).getTime();
            const now = Date.now();
            const isShortNotice = (aufgussDateTime - now) < (24 * 60 * 60 * 1000);
            const meisterId = aufgussToCancel.aufgussmeisterId;
            
            const newAufguesse = aufguesse.map(a =>
                a.id === aufgussId
                    ? { ...a, aufgussmeisterId: null, aufgussmeisterName: null, type: null }
                    : a
            );
            setAufguesse(newAufguesse);
            await apiClient.saveAufguesse(newAufguesse);
            
            const newUsers = users.map(u => {
                if (u.id === meisterId) {
                    const newCount = u.aufgussCount > 0 ? u.aufgussCount - 1 : 0;
                    const newCancellations = isShortNotice ? u.shortNoticeCancellations + 1 : u.shortNoticeCancellations;
                    return { ...u, aufgussCount: newCount, shortNoticeCancellations: newCancellations };
                }
                return u;
            });
            setUsers(newUsers);
            setCurrentUser(newUsers.find(u => u.id === currentUser!.id) || null);
            await apiClient.saveUsers(newUsers);
        }
    };

    const handleShareAufguss = async (aufguss: Aufguss) => {
        const dateStr = new Date(aufguss.date).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
        const postContent = `Ich übernehme den Aufguss am ${dateStr} um ${aufguss.time} Uhr in der ${aufguss.sauna} (${aufguss.location})! Es wird ein "${aufguss.type}" geben. Ich freue mich auf euch! 🔥`;
        await handleAddPost({ type: 'text', content: postContent });

        const now = Date.now();
        const newUsers = users.map(u => u.id === currentUser!.id ? { ...u, lastAufgussShareTimestamp: now } : u)
        setUsers(newUsers);
        setCurrentUser(newUsers.find(u => u.id === currentUser!.id) || null);
        await apiClient.saveUsers(newUsers);
    };
    
    const handleManageAufgussTypes = {
        onAddType: async (type: string) => {
            const newTypes = [...aufgussTypes, type];
            setAufgussTypes(newTypes);
            await apiClient.saveAufgussTypes(newTypes);
        },
        onDeleteType: async (type: string) => {
            const newTypes = aufgussTypes.filter(t => t !== type);
            setAufgussTypes(newTypes);
            await apiClient.saveAufgussTypes(newTypes);
        },
        onRenameType: async (oldType: string, newType: string) => {
            const newTypes = aufgussTypes.map(t => t === oldType ? newType : t);
            setAufgussTypes(newTypes);
            await apiClient.saveAufgussTypes(newTypes);
        },
    };
    
    // --- Festival Handlers ---
    const handleSelectFestival = async (id: string) => {
        setSelectedFestivalId(id);
        await apiClient.saveSelectedFestivalId(id);
    };

    const handleUpdateFestival = async (updatedFestival: Festival) => {
        const newFestivals = festivals.map(f => f.id === updatedFestival.id ? updatedFestival : f);
        setFestivals(newFestivals);
        await apiClient.saveFestivals(newFestivals);
    };

    const handleCreateFestival = async (festivalData: Omit<Festival, 'id' | 'participants' | 'tasks' | 'rsvpDeadline'>) => {
        const startDate = new Date(festivalData.startDate);
        const newFestival: Festival = {
            ...festivalData,
            id: `fest-${Date.now()}`,
            rsvpDeadline: getThursdayBefore(startDate).toISOString(),
            tasks: [],
            participants: users.map(u => ({
                userId: u.id,
                status: 'pending',
                aufgussAvailability: [],
                workHours: 0,
                hoursLogged: false,
                aufgussProposals: [],
            }))
        };
        const newFestivals = [...festivals, newFestival];
        setFestivals(newFestivals);
        await apiClient.saveFestivals(newFestivals);
        
        setSelectedFestivalId(newFestival.id);
        await apiClient.saveSelectedFestivalId(newFestival.id);
    };

    const onDeleteFestival = async (festivalId: string) => {
        if (window.confirm('Bist du sicher, dass du dieses Fest und alle zugehörigen Aufgaben löschen möchtest?')) {
            const newFestivals = festivals.filter(f => f.id !== festivalId);
            setFestivals(newFestivals);
            await apiClient.saveFestivals(newFestivals);
            
            if (selectedFestivalId === festivalId) {
                const newId = newFestivals.length > 0 ? newFestivals[0].id : '';
                setSelectedFestivalId(newId);
                await apiClient.saveSelectedFestivalId(newId);
            }
        }
    };

    const handleLogHours = async (festivalId: string, hours: number) => {
        if (!currentUser) return;
        // 1. Update festival participant data
        const newFestivals = festivals.map(f => {
            if (f.id === festivalId) {
                const updatedParticipants = f.participants.map(p =>
                    p.userId === currentUser.id ? { ...p, workHours: hours, hoursLogged: true } : p
                );
                return { ...f, participants: updatedParticipants };
            }
            return f;
        });
        setFestivals(newFestivals);
        await apiClient.saveFestivals(newFestivals);

        // 2. Update global user work hours
        const newUsers = users.map(u =>
            u.id === currentUser.id ? { ...u, workHours: u.workHours + hours } : u
        );
        setUsers(newUsers);
        await apiClient.saveUsers(newUsers);
    };
    
    // --- Other Handlers ---
    const handleGenerateCode = async () => {
        const newCode = Math.floor(100000 + Math.random() * 900000).toString();
        setRegistrationCode(newCode);
        await apiClient.saveRegistrationCode(newCode);
    };
    
    const getHolidayKey = (today: Date) => {
        const month = today.getMonth(); // 0-11
        const day = today.getDate();
        if ((month === 2 && day >= 29) || (month === 3 && day <= 1)) return 'easter';
        if (month === 11 && day >= 5 && day <= 7) return 'nikolaus';
        if (month === 11 && day >= 20 && day <= 27) return 'christmas';
        if (month === 11 && day >= 30 || (month === 0 && day <= 2)) return 'silvester';
        return null;
    };
    
    // --- Background Management ---
    const handleBackgroundUpload = (viewKey: string, file: File): Promise<void> => {
        return new Promise((resolve, reject) => {
            if (!file.type.startsWith('image/')) {
                reject(new Error('File is not an image.'));
                return;
            }

            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = async () => {
                    try {
                        const canvas = document.createElement('canvas');
                        const MAX_WIDTH = 1920;
                        const scaleFactor = img.width > MAX_WIDTH ? MAX_WIDTH / img.width : 1;
                        canvas.width = img.width * scaleFactor;
                        canvas.height = img.height * scaleFactor;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) {
                            reject(new Error('Could not get canvas context.'));
                            return;
                        }
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                        const dataUrl = canvas.toDataURL('image/jpeg', 0.8);

                        const newBackgrounds = { ...persistedBackgrounds, [viewKey]: dataUrl };
                        setPersistedBackgrounds(newBackgrounds);
                        await apiClient.saveBackgrounds(newBackgrounds);
                        resolve();
                    } catch (error) {
                        reject(error);
                    }
                };
                img.onerror = reject;
                img.src = e.target?.result as string;
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    };
    
    const handleRemoveBackground = async (viewKey: string) => {
        if(window.confirm(`Bist du sicher, dass du das Hintergrundbild für "${viewKey}" zurücksetzen möchtest?`)) {
            const newBackgrounds = { ...persistedBackgrounds };
            delete newBackgrounds[viewKey];
            setPersistedBackgrounds(newBackgrounds);
            await apiClient.saveBackgrounds(newBackgrounds);
        }
    };

    const backgroundUrl = useMemo(() => {
        const today = new Date();
        const holidayKey = getHoliday(today);
        const currentKey = appStage === 'loggedIn' ? view : appStage;
        const keyForLookup = holidayKey || currentKey;
        return persistedBackgrounds[keyForLookup] || FALLBACK_BACKGROUND_URLS[keyForLookup] || FALLBACK_BACKGROUND_URLS.dashboard;
    }, [view, appStage, persistedBackgrounds]);

    
    // --- RENDER LOGIC ---
    const userForProfilePage = useMemo(() => {
        const targetId = viewedUserId ?? currentUser?.id;
        return users.find(u => u.id === targetId);
    }, [viewedUserId, currentUser, users]);

    const renderContent = () => {
        if (!currentUser) return null; // Should not happen in loggedIn state

        switch (view) {
            case 'dashboard':
                return <Dashboard user={currentUser} setView={changeView} allUsers={users} allAufguesse={aufguesse} festivals={festivals} registrationCode={registrationCode} onGenerateCode={handleGenerateCode} persistedBackgrounds={persistedBackgrounds} onUploadBackground={handleBackgroundUpload} onRemoveBackground={handleRemoveBackground} />;
            case 'social':
                return <SocialFeed currentUser={currentUser} users={users} posts={posts} onAddPost={handleAddPost} onLikePost={handleLikePost} onAddComment={handleAddComment} onVote={onVote} onDeletePost={onDeletePost} onDeleteComment={onDeleteComment} />;
            case 'aufguss':
                return <AufgussPlanner user={currentUser} aufguesse={aufguesse} aufgussTypes={aufgussTypes} onClaimAufguss={handleClaimAufguss} onCancelAufguss={handleCancelAufguss} onShareAufguss={handleShareAufguss} onManageAufgussTypes={handleManageAufgussTypes}/>;
            case 'festival':
                 if (!selectedFestivalId && festivals.length > 0) {
                    return <div className="loading-spinner page-center"></div>;
                 }
                return <FestivalPlanner user={currentUser} users={users} festivals={festivals} selectedFestivalId={selectedFestivalId} onSelectFestival={handleSelectFestival} onUpdateFestival={handleUpdateFestival} onCreateFestival={handleCreateFestival} onDeleteFestival={onDeleteFestival} onLogHours={handleLogHours}/>;
            case 'mitglieder':
                return <MembersPage currentUser={currentUser} users={users} onViewProfile={(userId) => changeView('profile', userId)} onOpenPermissionsModal={handleOpenPermissionsModal} onOpenAwardsModal={handleOpenAwardsModal} onOpenQualsModal={handleOpenQualsModal} onDeleteUser={handleDeleteUser} />;
            case 'berichte':
                return <BerichtePage users={users} aufguesse={aufguesse}/>;
            case 'profile':
                if (userForProfilePage) {
                    return <ProfilePage currentUser={currentUser} viewedUser={userForProfilePage} onUpdateUser={handleUpdateUser} allAufguesse={aufguesse} allAwards={awards} onBackToList={viewedUserId ? handleBackToList : undefined} />;
                }
                return <div>Benutzer nicht gefunden.</div>;
            default:
                return <div>Not found</div>;
        }
    };

    const renderStage = () => {
        switch (appStage) {
            case 'loading':
                return <div className="loading-spinner page-center"></div>;
            case 'login':
                return <LoginPage onLogin={handleLogin} onGoToRegister={handleGoToRegister} />;
            case 'register':
                return <RegistrationPage code={registrationCode} onCodeSubmit={handleCodeSubmit} onBack={handleBackToLogin} />;
            case 'profile_setup':
                return <ProfileSetupPage onCompleteRegistration={handleCompleteRegistration} onBack={handleBackToLogin} />;
            case 'loggedIn':
                if (!currentUser) {
                    // This can happen briefly if state is inconsistent. Default to login.
                    setAppStage('login');
                    return <LoginPage onLogin={handleLogin} onGoToRegister={handleGoToRegister} />;
                }
                
                let activeViewForHeader: View = view;
                if (view === 'profile' && viewedUserId && viewedUserId !== currentUser.id) {
                    activeViewForHeader = 'mitglieder';
                } else if (view === 'profile' && (!viewedUserId || viewedUserId === currentUser.id)) {
                    activeViewForHeader = 'profile';
                }

                return (
                    <>
                        <Header user={currentUser} onLogout={memoizedOnLogout} setView={memoizedChangeView} activeView={activeViewForHeader} />
                        <main className="view-container">
                            {renderContent()}
                        </main>
                    </>
                );
            default:
                return <LoginPage onLogin={handleLogin} onGoToRegister={handleGoToRegister} />;
        }
    };

    return (
        <>
            <div id="app-background" style={{ backgroundImage: `url(${backgroundUrl})` }}></div>
            
            {renderStage()}
            
            {currentUser?.isAdmin && (
                <>
                    <PermissionEditModal 
                        isOpen={isPermissionsModalOpen}
                        onClose={() => setIsPermissionsModalOpen(false)}
                        user={editingUser}
                        onSave={handleSavePermissions}
                    />
                     <AwardEditModal
                        isOpen={isAwardModalOpen}
                        onClose={() => setIsAwardModalOpen(false)}
                        user={editingUser}
                        allAwards={awards}
                        awards={editingUser?.awards || []}
                        onSave={handleSaveAwards}
                        onCreateAward={handleCreateAward}
                    />
                    <QualificationAssignmentModal
                        isOpen={isQualsModalOpen}
                        onClose={() => setIsQualsModalOpen(false)}
                        user={editingUser}
                        allQuals={editingUser?.qualifications || []}
                        availableQuals={availableQuals}
                        onSave={handleSaveQuals}
                        onAddQual={handleAddQual}
                        onDeleteQual={handleDeleteQual}
                    />
                </>
            )}
        </>
    );
};
function RootApp() {
  const [user, setUser] = React.useState(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUser(data?.user ?? null)
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      setLoading(false)
    })

    return () => listener?.subscription.unsubscribe()
  }, [])

  if (loading) return <div className="login-container">Lade...</div>
  if (!user) return <LoginForm />

  return <SessionList />
}
const container = document.getElementById('root');
const root = createRoot(container!);
root.render(
  <React.StrictMode>
    <RootApp />
  </React.StrictMode>
);
