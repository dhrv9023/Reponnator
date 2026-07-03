import { useEffect, useRef, useState } from 'react';

interface UseTypewriterOptions {
  text: string;
  speed?: number;       // ms per character
  startDelay?: number;  // ms before typing begins
}

interface UseTypewriterReturn {
  displayed: string;
  done: boolean;
}

export default function useTypewriter({
  text,
  speed = 32,
  startDelay = 600,
}: UseTypewriterOptions): UseTypewriterReturn {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone]           = useState(false);
  const indexRef                  = useRef(0);

  useEffect(() => {
    // Reset when text changes
    setDisplayed('');
    setDone(false);
    indexRef.current = 0;

    let intervalId: ReturnType<typeof setInterval>;

    const timeoutId = setTimeout(() => {
      intervalId = setInterval(() => {
        if (indexRef.current < text.length) {
          const next = indexRef.current + 1;
          setDisplayed(text.slice(0, next));
          indexRef.current = next;
        } else {
          clearInterval(intervalId);
          setDone(true);
        }
      }, speed);
    }, startDelay);

    return () => {
      clearTimeout(timeoutId);
      clearInterval(intervalId);
    };
  }, [text, speed, startDelay]);

  return { displayed, done };
}
