/** Answer a question and check it against the official key (GATE's rules: MSQ needs the exact set, NAT a value in range). */
import { useState } from 'react';
import { answerText } from '../data';
import type { Question } from '../types';
import { CheckIcon, CrossIcon } from './Icons';

type Verdict = { correct: boolean; text: string } | null;

function check(q: Question, picked: string[], typed: string): Verdict {
  const answer = q.answer;
  if (!answer) return null;
  if (answer.kind === 'mta') return { correct: true, text: 'The official key gave every candidate the marks for this question.' };
  if (answer.kind === 'range') {
    const value = Number(typed.trim());
    if (typed.trim() === '' || Number.isNaN(value)) return { correct: false, text: 'Type a number first.' };
    const correct = value >= answer.low && value <= answer.high;
    const exact = answer.low === answer.high;
    if (correct) return { correct, text: exact ? `Correct: the key's answer is ${answer.low}.` : `Correct. The key accepts ${answerText(q)}.` };
    return { correct, text: exact ? `Not quite. The key's answer is ${answer.low}.` : `Not in the accepted range (${answerText(q)}).` };
  }
  if (picked.length === 0) return { correct: false, text: 'Pick an option first.' };
  const key = [...answer.options].sort().join(',');
  const mine = [...picked].sort().join(',');
  const correct = key === mine;
  if (q.type === 'MSQ') {
    return { correct, text: correct ? `Correct: ${answer.options.join(', ')}.` : `Not quite. The key is ${answer.options.join(', ')}; MSQ needs exactly the right set, with no partial marks.` };
  }
  const penalty = q.negative ? ` A wrong answer here costs ${q.negative < 0.5 ? '1/3' : '2/3'} mark.` : '';
  return { correct, text: correct ? `Correct: ${answer.options[0]}.` : `The key is ${answer.options[0]}.${penalty}` };
}

export function Practice({ question }: { question: Question }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [typed, setTyped] = useState('');
  const [verdict, setVerdict] = useState<Verdict>(null);
  const letters = question.options ? Object.keys(question.options) : ['A', 'B', 'C', 'D'];
  const multi = question.type === 'MSQ';

  const toggle = (letter: string) => {
    setVerdict(null);
    setPicked((current) => (multi ? (current.includes(letter) ? current.filter((l) => l !== letter) : [...current, letter]) : [letter]));
  };

  return (
    <form
      className="practice"
      onSubmit={(event) => {
        event.preventDefault();
        setVerdict(check(question, picked, typed));
      }}
    >
      <div className="field__label">
        {question.type === 'NAT' ? 'Your answer (a number)' : multi ? 'Pick every correct option' : 'Pick one option'}
      </div>
      {question.type === 'NAT' ? (
        <input
          id={`nat-${question.id}`}
          type="text"
          inputMode="decimal"
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
            setVerdict(null);
          }}
          aria-label="Your numerical answer"
          style={{ maxWidth: '12rem' }}
        />
      ) : (
        <div className="practice__options" role={multi ? 'group' : 'radiogroup'} aria-label="Options">
          {letters.map((letter) => (
            <label className="practice__option" key={letter}>
              <input
                type={multi ? 'checkbox' : 'radio'}
                name={`opt-${question.id}`}
                checked={picked.includes(letter)}
                onChange={() => toggle(letter)}
              />
              {letter}
            </label>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="btn" type="submit">
          Check answer
        </button>
        <button className="btn btn--quiet" type="button" onClick={() => setVerdict({ correct: true, text: `Official key: ${answerText(question)}.` })}>
          Show the key
        </button>
      </div>
      {verdict && (
        <div className={`result ${verdict.correct ? 'result--good' : 'result--bad'}`} role="status">
          {verdict.correct ? <CheckIcon /> : <CrossIcon />}
          <span>{verdict.text}</span>
        </div>
      )}
    </form>
  );
}
