// Node test runner for auth_storage.js
const assert = require('assert');
const fs = require('fs');

// Mock browser globals needed by auth_storage.js
global.window = global;
if (!global.window.crypto) {
    global.window.crypto = require('crypto').webcrypto;
}

// Mock IndexedDB
const mockDB = {
    credentials: new Map(),
    user_data: new Map(),
    remember_session: new Map()
};

global.window.indexedDB = {
    open: function(name, version) {
        const req = {
            result: {
                objectStoreNames: { contains: (s) => s in mockDB },
                createObjectStore: (s) => ({ createIndex: () => {} }),
                transaction: function(stores, mode) {
                    return {
                        objectStore: function(storeName) {
                            return {
                                get: function(key) {
                                    const getReq = {};
                                    setTimeout(() => {
                                        getReq.result = mockDB[storeName].get(key);
                                        if (getReq.onsuccess) getReq.onsuccess({ target: getReq });
                                    }, 5);
                                    return getReq;
                                },
                                put: function(val) {
                                    const putReq = {};
                                    setTimeout(() => {
                                        const key = val.key || val.email;
                                        mockDB[storeName].set(key, val);
                                        if (putReq.onsuccess) putReq.onsuccess({ target: putReq });
                                    }, 5);
                                    return putReq;
                                },
                                delete: function(key) {
                                    const delReq = {};
                                    setTimeout(() => {
                                        mockDB[storeName].delete(key);
                                        if (delReq.onsuccess) delReq.onsuccess({ target: delReq });
                                    }, 5);
                                    return delReq;
                                }
                            };
                        }
                    };
                }
            }
        };
        setTimeout(() => {
            if (req.onsuccess) req.onsuccess({ target: req });
        }, 5);
        return req;
    }
};

// Mock localStorage
const localStorageStore = new Map();
global.window.localStorage = {
    getItem: (k) => localStorageStore.get(k) || null,
    setItem: (k, v) => localStorageStore.set(k, String(v)),
    removeItem: (k) => localStorageStore.delete(k),
    clear: () => localStorageStore.clear()
};

// Mock document
global.window.document = {
    cookie: ""
};

// Load auth_storage.js
require('../static/js/auth_storage.js');

async function runTests() {
    console.log('--- Starting CocoScan Auth Storage Tests ---');

    // 1. Check exports
    assert(window.CocoScanAuth, 'CocoScanAuth should be defined on window');
    console.log('✓ CocoScanAuth exported properly');

    // 2. Test Role Normalization & Dashboard URLs
    assert.strictEqual(window.CocoScanAuth.normalizeRole('Farmer'), 'farmer');
    assert.strictEqual(window.CocoScanAuth.normalizeRole('admin'), 'admin');
    assert.strictEqual(window.CocoScanAuth.normalizeRole('agriculturist'), 'agri_expert');
    assert.strictEqual(window.CocoScanAuth.normalizeRole('agri_expert'), 'agri_expert');
    assert.strictEqual(window.CocoScanAuth.normalizeRole('lgu'), 'lgu');

    assert.strictEqual(window.CocoScanAuth.getRoleDashboardUrl('farmer'), '/farmer/dashboard');
    assert.strictEqual(window.CocoScanAuth.getRoleDashboardUrl('agri_expert'), '/agriculturist/dashboard');
    assert.strictEqual(window.CocoScanAuth.getRoleDashboardUrl('agriculturist'), '/agriculturist/dashboard');
    assert.strictEqual(window.CocoScanAuth.getRoleDashboardUrl('admin'), '/admin/dashboard');
    assert.strictEqual(window.CocoScanAuth.getRoleDashboardUrl('lgu'), '/lgu/dashboard');
    console.log('✓ Role normalization and dashboard URLs tested');

    // 3. Test Caching Credentials for Farmer
    const farmerRecord = await window.CocoScanAuth.cacheUserCredentials(
        'farmer1@cocoscan.local',
        'SecurePassword123!',
        'farmer',
        'Juan Dela Cruz',
        'user-uuid-1'
    );
    assert.strictEqual(farmerRecord.email, 'farmer1@cocoscan.local');
    assert.strictEqual(farmerRecord.role, 'farmer');
    assert(farmerRecord.salt && farmerRecord.salt.length === 32, 'Salt should be 16 bytes (32 hex characters)');
    assert(farmerRecord.passwordHash && farmerRecord.passwordHash.length === 64, 'Hash should be 32 bytes (64 hex characters)');
    console.log('✓ Farmer credential caching in IndexedDB tested');

    // 4. Test Caching Credentials for Admin & Agriculturist
    const adminRecord = await window.CocoScanAuth.cacheUserCredentials(
        'admin1@cocoscan.gov.ph',
        'AdminPass!@#456',
        'admin',
        'PCA Admin',
        'admin-uuid-1'
    );
    assert.strictEqual(adminRecord.email, 'admin1@cocoscan.gov.ph');
    assert.strictEqual(adminRecord.role, 'admin');

    const agriRecord = await window.CocoScanAuth.cacheUserCredentials(
        'agri1@cocoscan.gov.ph',
        'AgriPass!@#789',
        'agriculturist',
        'PCA Agriculturist',
        'agri-uuid-1'
    );
    assert.strictEqual(agriRecord.email, 'agri1@cocoscan.gov.ph');
    assert.strictEqual(agriRecord.role, 'agri_expert');
    console.log('✓ Admin and Agriculturist credential caching in IndexedDB tested');

    // 5. Test Offline Verification - Success
    const verifySuccess = await window.CocoScanAuth.verifyOfflineCredentials(
        'farmer1@cocoscan.local',
        'SecurePassword123!'
    );
    assert.strictEqual(verifySuccess.success, true);
    assert.strictEqual(verifySuccess.user.email, 'farmer1@cocoscan.local');
    assert.strictEqual(verifySuccess.user.role, 'farmer');
    assert.strictEqual(verifySuccess.user.name, 'Juan Dela Cruz');
    console.log('✓ Successful offline credential verification tested');

    // 6. Test Offline Verification - Incorrect Password
    const verifyWrongPass = await window.CocoScanAuth.verifyOfflineCredentials(
        'farmer1@cocoscan.local',
        'WrongPassword999!'
    );
    assert.strictEqual(verifyWrongPass.success, false);
    assert.match(verifyWrongPass.error, /Invalid email or password/i);
    console.log('✓ Rejected offline login with wrong password tested');

    // 7. Test Offline Verification - Nonexistent User
    const verifyNonexistent = await window.CocoScanAuth.verifyOfflineCredentials(
        'stranger@unknown.com',
        'SomePass123!'
    );
    assert.strictEqual(verifyNonexistent.success, false);
    assert.match(verifyNonexistent.error, /No offline credentials found/i);
    console.log('✓ Rejected offline login for uncached account tested');

    // 8. Test Metadata Updates
    const updateResult = await window.CocoScanAuth.updateCachedUserMetadata(
        'farmer1@cocoscan.local',
        { name: 'Juan D. Cruz (Senior Farmer)' }
    );
    assert.strictEqual(updateResult, true);
    const updatedUser = await window.CocoScanAuth.getCachedUser('farmer1@cocoscan.local');
    assert.strictEqual(updatedUser.name, 'Juan D. Cruz (Senior Farmer)');
    console.log('✓ Metadata update synchronization tested');

    // 9. Re-verify that password still works after metadata update
    const verifyAfterUpdate = await window.CocoScanAuth.verifyOfflineCredentials(
        'farmer1@cocoscan.local',
        'SecurePassword123!'
    );
    assert.strictEqual(verifyAfterUpdate.success, true);
    assert.strictEqual(verifyAfterUpdate.user.name, 'Juan D. Cruz (Senior Farmer)');
    console.log('✓ Password verification remains valid after metadata update');

    // 10. Test isInvalidProfileName
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName(null), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName(''), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('   '), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('None'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('none'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('None None'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('null'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('undefined'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('None Juan'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('Juan Dela Cruz'), false);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('Maria Santos'), false);
    console.log('✓ Profile name validation rules tested');

    // 11. Test sanitizeProfileName
    assert.strictEqual(window.CocoScanAuth.sanitizeProfileName('Juan Dela Cruz', 'farmer@cocoscan.local', 'Farmer'), 'Juan Dela Cruz');
    assert.strictEqual(window.CocoScanAuth.sanitizeProfileName('None', 'maria.santos@cocoscan.local', 'Farmer'), 'Maria Santos');
    assert.strictEqual(window.CocoScanAuth.sanitizeProfileName('None None', 'admin@cocoscan.gov.ph', 'Admin'), 'Admin');
    assert.strictEqual(window.CocoScanAuth.sanitizeProfileName(null, null, 'Farmer'), 'Farmer');
    console.log('✓ Profile name sanitization and email fallback tested');

    // 12. Test resolveSafeProfileName
    localStorageStore.clear();
    // Case A: Valid server name
    assert.strictEqual(window.CocoScanAuth.resolveSafeProfileName('Pedro Penduko', 'Farmer'), 'Pedro Penduko');
    assert.strictEqual(localStorageStore.get('cocoscan_user_name'), 'Pedro Penduko');

    // Case B: Server name is "None", but cached name is valid
    assert.strictEqual(window.CocoScanAuth.resolveSafeProfileName('None', 'Farmer'), 'Pedro Penduko');

    // Case C: Server name is "None", cached name is "None", email is set
    localStorageStore.set('cocoscan_user_name', 'None');
    localStorageStore.set('cocoscan_user_email', 'clara.reyes@cocoscan.local');
    assert.strictEqual(window.CocoScanAuth.resolveSafeProfileName('None', 'Farmer'), 'Clara Reyes');

    // Case D: All empty, fallback to default
    localStorageStore.clear();
    assert.strictEqual(window.CocoScanAuth.resolveSafeProfileName('None', 'Agriculturist'), 'Agriculturist');

    // Case E: Offline first name resolution with generic fallback server name
    localStorageStore.clear();
    localStorageStore.set('cocoscan_user_name', 'Maria Santos');
    assert.strictEqual(window.CocoScanAuth.resolveSafeFirstName('Farmer', 'Farmer'), 'Maria');

    // Case F: Offline first name resolution when cocoscan_user_first_name is stored
    localStorageStore.set('cocoscan_user_first_name', 'Juan');
    assert.strictEqual(window.CocoScanAuth.resolveSafeFirstName('Farmer', 'Farmer'), 'Juan');

    // Case G: Invalid generic role names in isInvalidProfileName
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('farmer'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('Farmer'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('administrator'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('agriculturist'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('lgu'), true);
    assert.strictEqual(window.CocoScanAuth.isInvalidProfileName('Maria'), false);

    console.log('✓ Safe profile name and first name resolution hierarchy tested');

    // 13. Test Dashboard Metrics Caching
    window.CocoScanAuth.cacheDashboardMetrics({
        total_cases: '14',
        pending_cases: '3',
        resolved_cases: '11',
        affected_areas: '5'
    }, 'farmer1@cocoscan.local');
    const retrievedMetrics = window.CocoScanAuth.getCachedDashboardMetrics('farmer1@cocoscan.local');
    assert(retrievedMetrics !== null, 'Metrics should be retrievable from cache');
    assert.strictEqual(retrievedMetrics.total_cases, '14');
    assert.strictEqual(retrievedMetrics.pending_cases, '3');
    assert.strictEqual(retrievedMetrics.resolved_cases, '11');
    assert.strictEqual(retrievedMetrics.affected_areas, '5');
    assert(retrievedMetrics.cached_at, 'cached_at timestamp should exist');
    console.log('✓ Dashboard metrics caching and retrieval tested');

    // 14. Test Chart Data Caching & Retrieval
    const sampleChartData = {
        trend_labels: ['Jan', 'Feb', 'Mar'],
        trend_datasets: [{ label: 'Cases', data: [2, 5, 8] }],
        distribution_labels: ['Rhinoceros Beetle', 'Brontispa'],
        distribution_data: [10, 4]
    };
    window.CocoScanAuth.cacheChartData(sampleChartData, 'farmer1@cocoscan.local');
    const retrievedCharts = window.CocoScanAuth.getCachedChartData('farmer1@cocoscan.local');
    assert(retrievedCharts !== null, 'Chart data should be retrievable from cache');
    assert.strictEqual(retrievedCharts.trend_labels.length, 3);
    assert.strictEqual(retrievedCharts.distribution_labels.length, 2);
    console.log('✓ Chart datasets caching and retrieval tested');

    // 15. Test Farmer Reports History Caching & IndexedDB Retrieval
    const sampleReports = [
        {
            id: 101,
            pest: 'Rhinoceros Beetle',
            status: 'Resolved',
            confidence: '95.4%',
            damage: 'High',
            date: '2026-09-10',
            timestamp: 'Sep 10, 2026 10:30 AM',
            location_text: 'Brgy. San Jose, San Pablo City',
            primary_image: 'https://images.unsplash.com/photo-1590005354167',
            notes: 'Observed bore holes near tree crown',
            expert_recommendations: ['Apply pheromone traps', 'Field sanitization'],
            chat_count: 3
        },
        {
            id: 102,
            pest: 'Brontispa',
            status: 'Under Review',
            confidence: '89.1%',
            damage: 'Moderate',
            date: '2026-09-12',
            timestamp: 'Sep 12, 2026 08:15 AM',
            location_text: 'Brgy. Del Remedio, San Pablo City',
            primary_image: 'https://images.unsplash.com/photo-1590005354168',
            notes: 'Young leaflets skeletonized',
            expert_recommendations: [],
            chat_count: 0
        }
    ];
    window.CocoScanAuth.cacheFarmerReports(sampleReports, 'farmer1@cocoscan.local');
    const retrievedReports = await window.CocoScanAuth.getCachedFarmerReports('farmer1@cocoscan.local');
    assert(Array.isArray(retrievedReports), 'Reports should be returned as array');
    assert.strictEqual(retrievedReports.length, 2);
    assert.strictEqual(retrievedReports[0].id, 101);
    assert.strictEqual(retrievedReports[0].pest, 'Rhinoceros Beetle');
    assert.strictEqual(retrievedReports[1].id, 102);
    assert.strictEqual(retrievedReports[1].pest, 'Brontispa');
    console.log('✓ Full farmer reports history caching & retrieval tested');

    // 16. Test Multi-Role Account Switching Offline
    // Step A: Agriculturist logs in offline
    const agriLogin = await window.CocoScanAuth.verifyOfflineCredentials(
        'agri1@cocoscan.gov.ph',
        'AgriPass!@#789'
    );
    assert.strictEqual(agriLogin.success, true);
    assert.strictEqual(agriLogin.user.role, 'agri_expert');
    assert.strictEqual(localStorageStore.get('cocoscan_user_role'), 'agri_expert');

    // Step B: User switches account to Farmer offline
    const farmerLogin = await window.CocoScanAuth.verifyOfflineCredentials(
        'farmer1@cocoscan.local',
        'SecurePassword123!'
    );
    assert.strictEqual(farmerLogin.success, true);
    assert.strictEqual(farmerLogin.user.role, 'farmer');
    assert.strictEqual(localStorageStore.get('cocoscan_user_role'), 'farmer');
    assert.strictEqual(localStorageStore.get('cocoscan_user_email'), 'farmer1@cocoscan.local');

    // Verify farmer offline session data is active
    const activeFarmerReports = await window.CocoScanAuth.getCachedFarmerReports();
    assert.strictEqual(activeFarmerReports.length, 2);
    console.log('✓ Multi-role account switching and session activation tested');

    // 17. Test Clear Active Session
    window.CocoScanAuth.clearActiveSession();
    assert.strictEqual(window.localStorage.getItem('cocoscan_user_role'), null);
    assert.strictEqual(window.localStorage.getItem('cocoscan_user_email'), null);
    assert.strictEqual(window.localStorage.getItem('cocoscan_offline_active'), null);
    console.log('✓ Clear active session tested');

    // 18. Test Farmer-exclusive Offline Remember Me Session
    // A) Setting remember me for farmer succeeds
    const setSuccess = await window.CocoScanAuth.setRememberMeSession(
        'farmer1@cocoscan.local',
        'farmer',
        'Juan Dela Cruz',
        'user-uuid-1',
        Date.now() + (90 * 86400 * 1000)
    );
    assert.strictEqual(setSuccess, true);
    assert.strictEqual(window.localStorage.getItem('cocoscan_remember_me'), 'true');
    assert.strictEqual(window.localStorage.getItem('cocoscan_user_role'), 'farmer');

    // B) Valid offline remember session check
    const hasValid = await window.CocoScanAuth.hasValidOfflineRememberSession();
    assert.strictEqual(hasValid, true);

    const retrievedSession = await window.CocoScanAuth.getRememberMeSession();
    assert(retrievedSession !== null);
    assert.strictEqual(retrievedSession.email, 'farmer1@cocoscan.local');
    assert.strictEqual(retrievedSession.role, 'farmer');
    assert.strictEqual(retrievedSession.name, 'Juan Dela Cruz');
    console.log('✓ Farmer offline Remember Me session storage and validation tested');

    // C) Non-farmers rejected from setting remember me
    const adminSet = await window.CocoScanAuth.setRememberMeSession(
        'admin1@cocoscan.local',
        'admin',
        'Admin User'
    );
    assert.strictEqual(adminSet, false);
    console.log('✓ Non-farmer roles correctly rejected from offline Remember Me');

    // D) Inactive > 30 days session auto-expires
    const expiredRecord = {
        key: 'active_farmer_session',
        email: 'inactive_farmer@cocoscan.local',
        role: 'farmer',
        name: 'Inactive Farmer',
        expiresAt: Date.now() + (60 * 86400 * 1000), // still within 90 days
        lastUsedAt: Date.now() - (31 * 86400 * 1000), // but inactive > 30 days
        createdAt: Date.now() - (31 * 86400 * 1000)
    };
    mockDB.remember_session.set('active_farmer_session', expiredRecord);
    const expiredCheck = await window.CocoScanAuth.getRememberMeSession();
    assert.strictEqual(expiredCheck, null);
    console.log('✓ Inactive (> 30 days) offline Remember Me session auto-expiration tested');

    // E) Clearing remember me session
    await window.CocoScanAuth.clearRememberMeSession();
    assert.strictEqual(window.localStorage.getItem('cocoscan_remember_me'), null);
    assert.strictEqual(await window.CocoScanAuth.hasValidOfflineRememberSession(), false);
    console.log('✓ Clear offline Remember Me session tested');

    console.log('\n ALL JAVASCRIPT AUTH STORAGE TESTS PASSED SUCCESSFULLY!');
}

runTests().catch((err) => {
    console.error('Test Failed:', err);
    process.exit(1);
});
