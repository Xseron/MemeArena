export interface User {
  id: number;
  username: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
  username: string;
}

export interface Player {
  id: number;
  username: string;
}

export type Phase = 'submitting' | 'voting' | 'results' | 'done';
export type RoomStatus = 'waiting' | 'playing' | 'finished';

export interface RoundDto {
  number: number;
  phase: Phase;
  phase_deadline: string;
}

export interface GameState {
  room: { status: RoomStatus };
  players: Player[];
  current_round: RoundDto | null;
}

export interface StateMessage {
  type: 'state';
  payload: GameState;
}
