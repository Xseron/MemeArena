import { Component } from '@angular/core';
import { CardHandComponent } from './components/card-hand/card-hand';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CardHandComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
