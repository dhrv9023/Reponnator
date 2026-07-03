import { useState, useEffect } from 'react';
import './index.css';
import VideoBackground from './components/VideoBackground';
import Navbar from './components/Navbar';
import HeroSection from './components/HeroSection';
import Workspace from './components/Workspace';
import HelpChat from './components/HelpChat';
import { StoryPage } from './components/Story';

export default function App() {
  const [view, setView] = useState<'hero' | 'ingestion' | 'workspace' | 'story'>('hero');
  const [isDark, setIsDark] = useState<boolean>(true);
  const [activeRepoKey, setActiveRepoKey] = useState<string>('karpathy__nanogpt');

  // Load theme on start
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    const darkActive = savedTheme === 'dark';
    setIsDark(darkActive);
    if (darkActive) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    
    // Load last active repo from localStorage
    const savedRepo = localStorage.getItem('activeRepoKey');
    if (savedRepo) {
      setActiveRepoKey(savedRepo);
    }
  }, []);
  
  // Save active repo to localStorage whenever it changes
  const handleRepoChange = (repoKey: string) => {
    setActiveRepoKey(repoKey);
    localStorage.setItem('activeRepoKey', repoKey);
  };

  const toggleTheme = () => {
    const newDark = !isDark;
    setIsDark(newDark);
    if (newDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  };

  return (
    <>
      {/* Layer 0 — full-screen dynamic 3D holographic background */}
      {view !== 'workspace' && view !== 'story' && <VideoBackground isDark={isDark} />}

      {/* Layer 10 — dynamic fixed navbar */}
      <Navbar
        currentView={view}
        setView={setView}
        isDark={isDark}
        toggleTheme={toggleTheme}
      />

      {/* Main view router */}
      <main>
        {view === 'story' ? (
          <StoryPage repoKey={activeRepoKey} />
        ) : view !== 'workspace' ? (
          <HeroSection
            currentView={view}
            setView={setView}
            isDark={isDark}
            onIngestComplete={(key) => {
              handleRepoChange(key);
              setView('workspace');
            }}
          />
        ) : (
          <Workspace repoKey={activeRepoKey} />
        )}
      </main>

      {/* Floating help chat widget */}
      <HelpChat />
    </>
  );
}
