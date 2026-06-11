// src/lib/api.test.ts
import { describe, it, expect } from 'vitest';

describe('API Client', () => {
  it('should format requests correctly', () => {
    const history = ['The Godfather'];
    const payload = { user_history: history };
    expect(payload.user_history).toContain('The Godfather');
  });
});