export const HAND_SIZE = 5;

export interface User {
  id: number;
  username: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
  username: string;
}

export interface MemeCard {
  id: number;
  title: string;
  image_url: string;
  caption: string;
}

export interface HandCard {
  id: number;
  meme_card: MemeCard;
}

export interface SubmissionDto {
  id: number;
  meme_card: MemeCard;
  player_id: number | null;
}

export interface Player {
  id: number;
  username: string;
  score: number;
}

export type Phase = 'submitting' | 'voting' | 'results' | 'done';
export type RoomStatus = 'waiting' | 'playing' | 'finished';

export interface RoundDto {
  number: number;
  phase: Phase;
  phase_deadline: string;
  situation: string;
  you_submitted: boolean;
  you_voted: boolean;
  your_hand: HandCard[];
  submissions: SubmissionDto[];
  winner_submission_id: number | null;
  vote_counts: Record<number, number>;
}

export interface FinalScore {
  player_id: number;
  score: number;
}

export interface RoundWinnerDto {
  user_id: number;
  username: string;
  meme_card: MemeCard;
  votes: number;
}

export interface RoundSummary {
  round_number: number;
  situation: string;
  winner: RoundWinnerDto | null;
}

export interface GameState {
  room: { status: RoomStatus };
  you_id: number;
  players: Player[];
  current_round: RoundDto | null;
  final_scores: FinalScore[] | null;
  round_summaries: RoundSummary[] | null;
}

export interface StateMessage {
  type: 'state';
  payload: GameState;
}

export interface ErrorMessage {
  type: 'error';
  payload: { code: string };
}

export type ServerMessage = StateMessage | ErrorMessage;
