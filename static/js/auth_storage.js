/**
 * CocoScan Local Authentication & Cryptographic Storage Utility
 * Manages local credential caching via IndexedDB and Web Cryptography API (PBKDF2-SHA256),
 * along with offline user data caching (dashboard metrics, charts, and full reports history).
 */

const AUTH_DB_NAME = 'cocoscan_auth_db';
const AUTH_DB_VERSION = 2;
const AUTH_STORE_NAME = 'credentials';
const USER_DATA_STORE_NAME = 'user_data';
const PBKDF2_ITERATIONS = 100000;

/**
 * Open or upgrade the CocoScan Auth IndexedDB database
 * @returns {Promise<IDBDatabase>}
 */
function openAuthDB() {
    return new Promise((resolve, reject) => {
        if (!('indexedDB' in window)) {
            reject(new Error('IndexedDB is not supported in this browser environment.'));
            return;
        }

        const request = window.indexedDB.open(AUTH_DB_NAME, AUTH_DB_VERSION);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(AUTH_STORE_NAME)) {
                const store = db.createObjectStore(AUTH_STORE_NAME, { keyPath: 'email' });
                store.createIndex('role', 'role', { unique: false });
                store.createIndex('updatedAt', 'updatedAt', { unique: false });
            }
            if (!db.objectStoreNames.contains(USER_DATA_STORE_NAME)) {
                const userDataStore = db.createObjectStore(USER_DATA_STORE_NAME, { keyPath: 'email' });
                userDataStore.createIndex('updatedAt', 'updatedAt', { unique: false });
            }
        };

        request.onsuccess = (event) => {
            resolve(event.target.result);
        };

        request.onerror = (event) => {
            console.error('[AuthDB] Error opening IndexedDB:', event.target.error);
            reject(event.target.error);
        };
    });
}

/**
 * Convert a Uint8Array buffer to a hex string
 * @param {Uint8Array} buffer 
 * @returns {string}
 */
function uint8ArrayToHex(buffer) {
    return Array.from(buffer)
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

/**
 * Convert a hex string to a Uint8Array buffer
 * @param {string} hexString 
 * @returns {Uint8Array}
 */
function hexToUint8Array(hexString) {
    if (!hexString || hexString.length % 2 !== 0) {
        return new Uint8Array();
    }
    const bytes = new Uint8Array(hexString.length / 2);
    for (let i = 0; i < hexString.length; i += 2) {
        bytes[i / 2] = parseInt(hexString.substr(i, 2), 16);
    }
    return bytes;
}

/**
 * Generate a cryptographically secure random salt hex string
 * @param {number} byteLength 
 * @returns {string}
 */
function generateSalt(byteLength = 16) {
    const array = new Uint8Array(byteLength);
    if (window.crypto && window.crypto.getRandomValues) {
        window.crypto.getRandomValues(array);
    } else {
        for (let i = 0; i < byteLength; i++) {
            array[i] = Math.floor(Math.random() * 256);
        }
    }
    return uint8ArrayToHex(array);
}

/**
 * Derive a PBKDF2-SHA256 password hash using the Web Crypto API
 * @param {string} password 
 * @param {string} saltHex 
 * @returns {Promise<string>}
 */
async function derivePasswordHash(password, saltHex) {
    const enc = new TextEncoder();
    const saltBytes = hexToUint8Array(saltHex);

    if (window.crypto && window.crypto.subtle) {
        try {
            const keyMaterial = await window.crypto.subtle.importKey(
                'raw',
                enc.encode(password),
                { name: 'PBKDF2' },
                false,
                ['deriveBits']
            );

            const derivedBits = await window.crypto.subtle.deriveBits(
                {
                    name: 'PBKDF2',
                    salt: saltBytes,
                    iterations: PBKDF2_ITERATIONS,
                    hash: 'SHA-256'
                },
                keyMaterial,
                256
            );

            return uint8ArrayToHex(new Uint8Array(derivedBits));
        } catch (subtleErr) {
            console.warn('[AuthDB] SubtleCrypto derivation failed, using SHA-256 fallback:', subtleErr);
        }
    }

    // Fallback using SubtleCrypto digest if PBKDF2 key import fails
    if (window.crypto && window.crypto.subtle) {
        const combined = enc.encode(saltHex + ':' + password);
        const hashBuffer = await window.crypto.subtle.digest('SHA-256', combined);
        return uint8ArrayToHex(new Uint8Array(hashBuffer));
    }

    // Ultimate fallback for restricted environments
    let hash = 0;
    const str = saltHex + ':' + password;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash).toString(16).padStart(64, '0');
}

/**
 * Normalize role string
 * @param {string} role 
 * @returns {string}
 */
function normalizeAuthRole(role) {
    const raw = String(role || '').trim().toLowerCase();
    if (raw === 'admin' || raw === 'administrator') return 'admin';
    if (raw === 'agri_expert' || raw === 'agriculturist' || raw === 'expert' || raw === 'agriculture_expert') return 'agri_expert';
    if (raw === 'lgu' || raw === 'lgu_officer') return 'lgu';
    if (raw === 'farmer') return 'farmer';
    return raw || 'farmer';
}

/**
 * Get role dashboard URL
 * @param {string} role 
 * @returns {string}
 */
function getAuthRoleDashboardUrl(role) {
    const norm = normalizeAuthRole(role);
    if (norm === 'farmer') return '/farmer/dashboard';
    if (norm === 'agri_expert') return '/agriculturist/dashboard';
    if (norm === 'admin') return '/admin/dashboard';
    if (norm === 'lgu') return '/lgu/dashboard';
    return '/login';
}

/**
 * Check if a given profile name is null, undefined, 'None', 'null', or empty
 * @param {string} name 
 * @returns {boolean}
 */
function isInvalidProfileName(name) {
    if (!name) return true;
    const clean = String(name).trim().toLowerCase();
    return clean === '' ||
           clean === 'none' ||
           clean === 'none none' ||
           clean === 'null' ||
           clean === 'undefined' ||
           clean === 'farmer' ||
           clean === 'farmer (offline)' ||
           clean === 'account' ||
           clean === 'user' ||
           clean === 'administrator' ||
           clean === 'agriculturist' ||
           clean === 'lgu' ||
           clean === 'lgu officer' ||
           clean.startsWith('none ');
}

/**
 * Sanitize and resolve a clean profile name from server response, email, or fallback
 * @param {string} name 
 * @param {string} email 
 * @param {string} defaultName 
 * @returns {string}
 */
function sanitizeProfileName(name, email, defaultName = 'Farmer') {
    if (!isInvalidProfileName(name)) {
        return String(name).trim();
    }
    if (email && email.includes('@')) {
        const derived = email.split('@')[0].replace(/[._-]/g, ' ').trim();
        if (derived && !isInvalidProfileName(derived)) {
            return derived.split(/\s+/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        }
    }
    return defaultName;
}

/**
 * Resolve profile name safely by prioritizing valid cached active user name, active email derivation, then server name
 * @param {string} serverName 
 * @param {string} defaultRoleName 
 * @param {string} activeEmail
 * @returns {string}
 */
function resolveSafeProfileName(serverName, defaultRoleName = 'Farmer', activeEmail = null) {
    const isOffline = typeof navigator !== 'undefined' && (!navigator.onLine || (typeof localStorage !== 'undefined' && localStorage.getItem('cocoscan_offline_active') === 'true'));
    const cachedName = typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_name') : null;
    const cachedFirstName = typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_first_name') : null;
    const cachedEmail = activeEmail || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null);

    // In offline mode, prioritize active cached user metadata to prevent stale server templates from overwriting
    if (isOffline) {
        if (!isInvalidProfileName(cachedName)) {
            return String(cachedName).trim();
        }
        if (!isInvalidProfileName(cachedFirstName)) {
            return String(cachedFirstName).trim();
        }
        if (cachedEmail && cachedEmail.includes('@')) {
            const derived = cachedEmail.split('@')[0].replace(/[._-]/g, ' ').trim();
            if (derived && !isInvalidProfileName(derived)) {
                const formatted = derived.split(/\s+/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                if (typeof localStorage !== 'undefined') localStorage.setItem('cocoscan_user_name', formatted);
                return formatted;
            }
        }
    }

    // Online mode: check server name first
    if (!isInvalidProfileName(serverName)) {
        const cleanServer = String(serverName).trim();
        if (typeof localStorage !== 'undefined') localStorage.setItem('cocoscan_user_name', cleanServer);
        return cleanServer;
    }

    if (!isInvalidProfileName(cachedName)) {
        return String(cachedName).trim();
    }

    if (!isInvalidProfileName(cachedFirstName)) {
        return String(cachedFirstName).trim();
    }

    if (cachedEmail && cachedEmail.includes('@')) {
        const derived = cachedEmail.split('@')[0].replace(/[._-]/g, ' ').trim();
        if (derived && !isInvalidProfileName(derived)) {
            const formatted = derived.split(/\s+/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            if (typeof localStorage !== 'undefined') localStorage.setItem('cocoscan_user_name', formatted);
            return formatted;
        }
    }

    return defaultRoleName;
}

/**
 * Resolve the user's first name safely from cached storage, profile name, or email derivation
 * @param {string} serverName 
 * @param {string} defaultRoleName 
 * @param {string} activeEmail 
 * @returns {string}
 */
function resolveSafeFirstName(serverName, defaultRoleName = 'Farmer', activeEmail = null) {
    const cachedFirstName = typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_first_name') : null;
    if (!isInvalidProfileName(cachedFirstName)) {
        return String(cachedFirstName).trim();
    }

    const fullName = resolveSafeProfileName(serverName, defaultRoleName, activeEmail);
    if (!isInvalidProfileName(fullName)) {
        const first = fullName.trim().split(/\s+/)[0];
        if (first && !isInvalidProfileName(first)) {
            if (typeof localStorage !== 'undefined' && !localStorage.getItem('cocoscan_user_first_name')) {
                localStorage.setItem('cocoscan_user_first_name', first);
            }
            return first;
        }
    }

    const cachedEmail = activeEmail || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null);
    if (cachedEmail && cachedEmail.includes('@')) {
        const firstSegment = cachedEmail.split('@')[0].split(/[._-]/)[0].trim();
        if (firstSegment && !isInvalidProfileName(firstSegment)) {
            const formatted = firstSegment.charAt(0).toUpperCase() + firstSegment.slice(1);
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem('cocoscan_user_first_name', formatted);
            }
            return formatted;
        }
    }

    return defaultRoleName;
}

/**
 * Cache user credentials securely in IndexedDB
 * @param {string} email 
 * @param {string} password 
 * @param {string} role 
 * @param {string} name 
 * @param {string} userId 
 * @returns {Promise<Object>}
 */
async function cacheUserCredentials(email, password, role, name, userId) {
    if (!email || !password) {
        throw new Error('Email and password are required for local credential caching.');
    }

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedRole = normalizeAuthRole(role);
    const safeName = sanitizeProfileName(name, normalizedEmail, normalizedRole === 'farmer' ? 'Farmer' : 'User');
    const salt = generateSalt(16);
    const passwordHash = await derivePasswordHash(password, salt);

    const userRecord = {
        email: normalizedEmail,
        passwordHash: passwordHash,
        salt: salt,
        role: normalizedRole,
        name: safeName,
        userId: userId || null,
        updatedAt: new Date().toISOString()
    };

    const db = await openAuthDB();
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([AUTH_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE_NAME);
        const putRequest = store.put(userRecord);

        putRequest.onsuccess = () => {
            // Also synchronize active session metadata in localStorage
            localStorage.setItem('cocoscan_user_role', normalizedRole);
            localStorage.setItem('cocoscan_user_email', normalizedEmail);
            localStorage.setItem('cocoscan_user_name', safeName);
            const firstPart = safeName && !isInvalidProfileName(safeName) ? safeName.split(/\s+/)[0] : '';
            if (firstPart && !isInvalidProfileName(firstPart)) {
                localStorage.setItem('cocoscan_user_first_name', firstPart);
            }
            if (userId) localStorage.setItem('cocoscan_user_id', userId);
            resolve(userRecord);
        };

        putRequest.onerror = (event) => {
            console.error('[AuthDB] Failed to cache user credentials:', event.target.error);
            reject(event.target.error);
        };
    });
}

/**
 * Verify user credentials offline against locally cached credentials
 * @param {string} email 
 * @param {string} password 
 * @returns {Promise<{success: boolean, user?: Object, error?: string}>}
 */
async function verifyOfflineCredentials(email, password) {
    if (!email || !password) {
        return { success: false, error: 'Please enter both email and password.' };
    }

    const normalizedEmail = email.trim().toLowerCase();

    try {
        const db = await openAuthDB();
        const userRecord = await new Promise((resolve, reject) => {
            const transaction = db.transaction([AUTH_STORE_NAME], 'readonly');
            const store = transaction.objectStore(AUTH_STORE_NAME);
            const getRequest = store.get(normalizedEmail);

            getRequest.onsuccess = () => resolve(getRequest.result);
            getRequest.onerror = (e) => reject(e.target.error);
        });

        if (!userRecord || !userRecord.passwordHash || !userRecord.salt) {
            return {
                success: false,
                error: 'No offline credentials found for this account. Please connect to the internet to log in at least once.'
            };
        }

        const computedHash = await derivePasswordHash(password, userRecord.salt);
        if (computedHash !== userRecord.passwordHash) {
            return {
                success: false,
                error: 'Invalid email or password. Offline verification failed.'
            };
        }

        const safeName = sanitizeProfileName(userRecord.name, normalizedEmail, userRecord.role === 'farmer' ? 'Farmer' : 'User');

        if (typeof localStorage !== 'undefined') {
            localStorage.setItem('cocoscan_user_role', userRecord.role);
            localStorage.setItem('cocoscan_user_email', normalizedEmail);
            localStorage.setItem('cocoscan_user_name', safeName);
            const firstPart = safeName && !isInvalidProfileName(safeName) ? safeName.split(/\s+/)[0] : '';
            if (firstPart && !isInvalidProfileName(firstPart)) {
                localStorage.setItem('cocoscan_user_first_name', firstPart);
            }
            if (userRecord.userId) localStorage.setItem('cocoscan_user_id', userRecord.userId);
            localStorage.setItem('cocoscan_offline_active', 'true');
        }
        if (typeof document !== 'undefined') {
            document.cookie = "cocoscan_offline_active=true; path=/; max-age=86400; SameSite=Lax";
            document.cookie = "cocoscan_user_role=" + encodeURIComponent(userRecord.role) + "; path=/; max-age=86400; SameSite=Lax";
            document.cookie = "cocoscan_user_email=" + encodeURIComponent(normalizedEmail) + "; path=/; max-age=86400; SameSite=Lax";
        }

        // Activate user offline session data
        await activateUserOfflineSession(normalizedEmail);

        return {
            success: true,
            user: {
                email: userRecord.email,
                role: userRecord.role,
                name: safeName,
                userId: userRecord.userId,
                updatedAt: userRecord.updatedAt
            }
        };
    } catch (err) {
        console.error('[AuthDB] Offline verification error:', err);
        return {
            success: false,
            error: 'An error occurred during offline authentication. Please try again.'
        };
    }
}

/**
 * Retrieve a cached user record by email without sensitive hash
 * @param {string} email 
 * @returns {Promise<Object|null>}
 */
async function getCachedUser(email) {
    if (!email) return null;
    try {
        const db = await openAuthDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([AUTH_STORE_NAME], 'readonly');
            const store = transaction.objectStore(AUTH_STORE_NAME);
            const req = store.get(email.trim().toLowerCase());
            req.onsuccess = () => {
                if (req.result) {
                    const { passwordHash, salt, ...safeData } = req.result;
                    safeData.name = sanitizeProfileName(safeData.name, safeData.email, safeData.role === 'farmer' ? 'Farmer' : 'User');
                    resolve(safeData);
                } else {
                    resolve(null);
                }
            };
            req.onerror = (e) => reject(e.target.error);
        });
    } catch (e) {
        console.warn('[AuthDB] Failed to retrieve cached user:', e);
        return null;
    }
}

/**
 * Update cached user metadata (role, name, userId) without changing the password hash
 * @param {string} email 
 * @param {Object} metadata 
 * @returns {Promise<boolean>}
 */
async function updateCachedUserMetadata(email, metadata = {}) {
    if (!email) return false;
    try {
        const normalizedEmail = email.trim().toLowerCase();
        const db = await openAuthDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([AUTH_STORE_NAME], 'readwrite');
            const store = transaction.objectStore(AUTH_STORE_NAME);
            const getReq = store.get(normalizedEmail);

            getReq.onsuccess = () => {
                const record = getReq.result;
                if (!record) {
                    resolve(false);
                    return;
                }

                if (metadata.role) record.role = normalizeAuthRole(metadata.role);
                if (metadata.name && !isInvalidProfileName(metadata.name)) {
                    record.name = String(metadata.name).trim();
                }
                if (metadata.userId) record.userId = metadata.userId;
                record.updatedAt = new Date().toISOString();

                const putReq = store.put(record);
                putReq.onsuccess = () => resolve(true);
                putReq.onerror = (e) => reject(e.target.error);
            };

            getReq.onerror = (e) => reject(e.target.error);
        });
    } catch (e) {
        console.warn('[AuthDB] Failed to update user metadata:', e);
        return false;
    }
}

/**
 * Save user dashboard data (metrics, charts, reports) into IndexedDB user_data store
 * @param {string} email 
 * @param {Object} data 
 * @returns {Promise<boolean>}
 */
async function saveUserData(email, data = {}) {
    if (!email) return false;
    try {
        const normalizedEmail = email.trim().toLowerCase();
        const db = await openAuthDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([USER_DATA_STORE_NAME], 'readwrite');
            const store = transaction.objectStore(USER_DATA_STORE_NAME);
            const getReq = store.get(normalizedEmail);

            getReq.onsuccess = () => {
                const existing = getReq.result || { email: normalizedEmail };
                const merged = {
                    ...existing,
                    ...data,
                    email: normalizedEmail,
                    updatedAt: new Date().toISOString()
                };
                const putReq = store.put(merged);
                putReq.onsuccess = () => resolve(true);
                putReq.onerror = (e) => reject(e.target.error);
            };
            getReq.onerror = (e) => reject(e.target.error);
        });
    } catch (e) {
        console.warn('[AuthDB] Failed to save user data in IndexedDB:', e);
        return false;
    }
}

/**
 * Retrieve user dashboard data from IndexedDB user_data store
 * @param {string} email 
 * @returns {Promise<Object|null>}
 */
async function getUserData(email) {
    if (!email) return null;
    try {
        const normalizedEmail = email.trim().toLowerCase();
        const db = await openAuthDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([USER_DATA_STORE_NAME], 'readonly');
            const store = transaction.objectStore(USER_DATA_STORE_NAME);
            const getReq = store.get(normalizedEmail);
            getReq.onsuccess = () => resolve(getReq.result || null);
            getReq.onerror = (e) => reject(e.target.error);
        });
    } catch (e) {
        console.warn('[AuthDB] Failed to get user data from IndexedDB:', e);
        return null;
    }
}

/**
 * Securely cache dashboard statistics in LocalStorage & IndexedDB
 * @param {Object} metrics 
 * @param {string} email
 */
function cacheDashboardMetrics(metrics, email = null) {
    if (!metrics || typeof metrics !== 'object') return;
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();
    const metricsPayload = {
        total_cases: String(metrics.total_cases ?? '0'),
        pending_cases: String(metrics.pending_cases ?? '0'),
        resolved_cases: String(metrics.resolved_cases ?? '0'),
        affected_areas: String(metrics.affected_areas ?? '0'),
        cached_at: new Date().toISOString()
    };

    try {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem('cocoscan_cached_metrics', JSON.stringify(metricsPayload));
            if (targetEmail) {
                localStorage.setItem(`cocoscan_cached_metrics_${targetEmail}`, JSON.stringify(metricsPayload));
            }
        }
    } catch (e) {
        console.warn('[AuthDB] Failed to cache dashboard metrics in LocalStorage:', e);
    }

    if (targetEmail) {
        saveUserData(targetEmail, { metrics: metricsPayload }).catch(err => {
            console.debug('[AuthDB] IndexedDB metrics save note:', err);
        });
    }
}

/**
 * Retrieve cached dashboard statistics from LocalStorage or IndexedDB
 * @param {string} email
 * @returns {Object|null}
 */
function getCachedDashboardMetrics(email = null) {
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();
    try {
        if (typeof localStorage !== 'undefined') {
            if (targetEmail) {
                const userRaw = localStorage.getItem(`cocoscan_cached_metrics_${targetEmail}`);
                if (userRaw) return JSON.parse(userRaw);
            }
            const raw = localStorage.getItem('cocoscan_cached_metrics');
            return raw ? JSON.parse(raw) : null;
        }
    } catch (e) {
        return null;
    }
    return null;
}

/**
 * Securely cache dashboard chart datasets in LocalStorage & IndexedDB
 * @param {Object} chartData 
 * @param {string} email 
 */
function cacheChartData(chartData, email = null) {
    if (!chartData || typeof chartData !== 'object') return;
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();
    const payload = {
        trend_labels: Array.isArray(chartData.trend_labels) ? chartData.trend_labels : [],
        trend_datasets: Array.isArray(chartData.trend_datasets) ? chartData.trend_datasets : [],
        distribution_labels: Array.isArray(chartData.distribution_labels) ? chartData.distribution_labels : [],
        distribution_data: Array.isArray(chartData.distribution_data) ? chartData.distribution_data : [],
        cached_at: new Date().toISOString()
    };

    try {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem('cocoscan_cached_charts', JSON.stringify(payload));
            if (targetEmail) {
                localStorage.setItem(`cocoscan_cached_charts_${targetEmail}`, JSON.stringify(payload));
            }
        }
    } catch (e) {
        console.warn('[AuthDB] Failed to cache chart data in LocalStorage:', e);
    }

    if (targetEmail) {
        saveUserData(targetEmail, { chart_data: payload }).catch(err => {
            console.debug('[AuthDB] IndexedDB chart save note:', err);
        });
    }
}

/**
 * Retrieve cached chart data from LocalStorage
 * @param {string} email 
 * @returns {Object|null}
 */
function getCachedChartData(email = null) {
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();
    try {
        if (typeof localStorage !== 'undefined') {
            if (targetEmail) {
                const userRaw = localStorage.getItem(`cocoscan_cached_charts_${targetEmail}`);
                if (userRaw) return JSON.parse(userRaw);
            }
            const raw = localStorage.getItem('cocoscan_cached_charts');
            return raw ? JSON.parse(raw) : null;
        }
    } catch (e) {
        return null;
    }
    return null;
}

/**
 * Cache full farmer reports history in IndexedDB and LocalStorage
 * @param {Array} reports 
 * @param {string} email 
 */
function cacheFarmerReports(reports, email = null) {
    if (!Array.isArray(reports)) return;
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();

    try {
        if (typeof localStorage !== 'undefined') {
            const serialized = JSON.stringify(reports);
            localStorage.setItem('cocoscan_cached_farmer_reports', serialized);
            if (targetEmail) {
                localStorage.setItem(`cocoscan_cached_farmer_reports_${targetEmail}`, serialized);
            }
        }
    } catch (e) {
        console.warn('[AuthDB] LocalStorage quota reached while caching reports; IndexedDB will serve as primary:', e);
    }

    if (targetEmail) {
        saveUserData(targetEmail, { reports: reports }).catch(err => {
            console.warn('[AuthDB] Failed to cache reports in IndexedDB:', err);
        });
    }
}

/**
 * Retrieve cached farmer reports history from IndexedDB and/or LocalStorage
 * @param {string} email 
 * @returns {Promise<Array>}
 */
async function getCachedFarmerReports(email = null) {
    const targetEmail = (email || (typeof localStorage !== 'undefined' ? localStorage.getItem('cocoscan_user_email') : null) || '').trim().toLowerCase();

    // 1. Try IndexedDB first (most reliable, holds full datasets without quota restrictions)
    if (targetEmail) {
        try {
            const userData = await getUserData(targetEmail);
            if (userData && Array.isArray(userData.reports) && userData.reports.length > 0) {
                return userData.reports;
            }
        } catch (e) {
            console.debug('[AuthDB] IndexedDB reports retrieval note:', e);
        }
    }

    // 2. Fallback to LocalStorage
    try {
        if (typeof localStorage !== 'undefined') {
            if (targetEmail) {
                const userRaw = localStorage.getItem(`cocoscan_cached_farmer_reports_${targetEmail}`);
                if (userRaw) {
                    const parsed = JSON.parse(userRaw);
                    if (Array.isArray(parsed)) return parsed;
                }
            }
            const raw = localStorage.getItem('cocoscan_cached_farmer_reports');
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) return parsed;
            }
        }
    } catch (e) {
        console.warn('[AuthDB] LocalStorage reports parse error:', e);
    }

    return [];
}

/**
 * Activate a user's offline session state in LocalStorage when logging in offline
 * @param {string} email 
 */
async function activateUserOfflineSession(email) {
    if (!email) return;
    const normalizedEmail = email.trim().toLowerCase();

    try {
        const userData = await getUserData(normalizedEmail);
        if (userData && typeof localStorage !== 'undefined') {
            if (userData.metrics) {
                localStorage.setItem('cocoscan_cached_metrics', JSON.stringify(userData.metrics));
                localStorage.setItem(`cocoscan_cached_metrics_${normalizedEmail}`, JSON.stringify(userData.metrics));
            }
            if (userData.chart_data) {
                localStorage.setItem('cocoscan_cached_charts', JSON.stringify(userData.chart_data));
                localStorage.setItem(`cocoscan_cached_charts_${normalizedEmail}`, JSON.stringify(userData.chart_data));
            }
            if (Array.isArray(userData.reports) && userData.reports.length > 0) {
                try {
                    localStorage.setItem('cocoscan_cached_farmer_reports', JSON.stringify(userData.reports));
                    localStorage.setItem(`cocoscan_cached_farmer_reports_${normalizedEmail}`, JSON.stringify(userData.reports));
                } catch (quotaErr) {
                    console.debug('[AuthDB] LocalStorage quota limit during session activation (IndexedDB holds data):', quotaErr);
                }
            }
        }
    } catch (e) {
        console.warn('[AuthDB] Session activation note:', e);
    }
}

/**
 * Cleanly clear active session state for account switching without deleting cached offline credentials or data
 */
function clearActiveSession() {
    if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('cocoscan_offline_active');
        localStorage.removeItem('cocoscan_user_role');
        localStorage.removeItem('cocoscan_user_email');
        localStorage.removeItem('cocoscan_user_name');
        localStorage.removeItem('cocoscan_user_first_name');
        localStorage.removeItem('cocoscan_user_id');
    }
    if (typeof document !== 'undefined') {
        document.cookie = "cocoscan_offline_active=; path=/; max-age=0";
        document.cookie = "cocoscan_user_role=; path=/; max-age=0";
        document.cookie = "cocoscan_user_email=; path=/; max-age=0";
    }
}

// Export functions to global scope for PWA and HTML templates
if (typeof window !== 'undefined') {
    window.CocoScanAuth = {
        openAuthDB,
        derivePasswordHash,
        cacheUserCredentials,
        verifyOfflineCredentials,
        getCachedUser,
        updateCachedUserMetadata,
        normalizeRole: normalizeAuthRole,
        getRoleDashboardUrl: getAuthRoleDashboardUrl,
        isInvalidProfileName,
        sanitizeProfileName,
        resolveSafeProfileName,
        resolveSafeFirstName,
        saveUserData,
        getUserData,
        cacheDashboardMetrics,
        getCachedDashboardMetrics,
        cacheChartData,
        getCachedChartData,
        cacheFarmerReports,
        getCachedFarmerReports,
        activateUserOfflineSession,
        clearActiveSession
    };
}
