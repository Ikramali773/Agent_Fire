// Mirrors the backend's _MIN_PASSWORD_LENGTH (app/api/auth.py). Duplicated
// rather than fetched because a length rule is not worth a round trip, and
// the server enforces it regardless - this only saves the user a rejected
// submit.
export const MIN_PASSWORD_LENGTH = 8;
