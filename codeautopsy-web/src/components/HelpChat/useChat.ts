import { useState, useEffect, useCallback, useRef } from "react";
import { FLOW, FlowOption } from "./chatFlow";
import { KNOWLEDGE_CARD } from "./knowledgeCard";

export interface ChatMessage {
  id: string;
  type: "bot" | "user";
  text: string;
  timestamp: Date;
}

export interface CustomOption {
  label: string;
  next?: string;
  action?: string;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentNodeId, setCurrentNodeId] = useState<string>("root");
  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [conversationPath, setConversationPath] = useState<string[]>(["root"]);
  const [emailSubject, setEmailSubject] = useState<string>("");
  const [showEmailForm, setShowEmailForm] = useState<boolean>(false);
  const [emailSent, setEmailSent] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string>("");

  // Track active custom options (e.g., after email submission)
  const [customOptions, setCustomOptions] = useState<CustomOption[] | null>(null);

  // Transition state for option click animation
  const [selectedOption, setSelectedOption] = useState<FlowOption | CustomOption | null>(null);
  const [isTransitioningOptions, setIsTransitioningOptions] = useState<boolean>(false);

  // To prevent multiple trigger timeouts and duplicate messages
  const typingTimeoutRef = useRef<any>(null);

  // Generate UUID on mount
  useEffect(() => {
    const uuid = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    setSessionId(uuid);
  }, []);

  const openChat = useCallback(() => {
    setIsOpen(true);
  }, []);

  const closeChat = useCallback(() => {
    setIsOpen(false);
  }, []);

  // Initialize initial message on mount
  useEffect(() => {
    const rootNode = FLOW.root;
    if (rootNode) {
      setIsTyping(true);
      const timer = setTimeout(() => {
        setMessages([
          {
            id: "init-bot",
            type: "bot",
            text: rootNode.message,
            timestamp: new Date(),
          },
        ]);
        setIsTyping(false);
      }, 800);

      return () => clearTimeout(timer);
    }
  }, []);

  const resetChat = useCallback(() => {
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    setCurrentNodeId("root");
    setConversationPath(["root"]);
    setEmailSubject("");
    setShowEmailForm(false);
    setEmailSent(false);
    setCustomOptions(null);
    setSelectedOption(null);
    setIsTransitioningOptions(false);
    setIsTyping(true);

    const rootNode = FLOW.root;
    setMessages([
      {
        id: `reset-bot-${Date.now()}`,
        type: "bot",
        text: rootNode.message,
        timestamp: new Date(),
      },
    ]);

    const timer = setTimeout(() => {
      setIsTyping(false);
    }, 800);

    typingTimeoutRef.current = timer;
  }, []);

  const handleOptionSelect = useCallback(
    (option: FlowOption | CustomOption) => {
      if (isTransitioningOptions || isTyping) return;

      // 1. Enter click transition state
      setSelectedOption(option);
      setIsTransitioningOptions(true);

      // Wait 300ms for button animation
      setTimeout(() => {
        // Clear transition state and option buttons disappear
        setIsTransitioningOptions(false);
        setSelectedOption(null);

        // 2. Add user message bubble
        const userMsgId = `user-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          {
            id: userMsgId,
            type: "user",
            text: option.label,
            timestamp: new Date(),
          },
        ]);

        // 3. Handle custom action (e.g. closing chat or starting over)
        if ("action" in option && option.action === "close") {
          closeChat();
          return;
        }

        const nextNodeId = option.next;
        if (nextNodeId === "root") {
          resetChat();
          return;
        }

        // 4. Handle email gateway entry
        const currentNode = FLOW[currentNodeId];
        const flowOption = option as FlowOption;
        if (currentNode?.isEmailGateway && flowOption.emailSubject) {
          setEmailSubject(flowOption.emailSubject);
          setShowEmailForm(true);
          return;
        }

        if (!nextNodeId) return;

        // 5. Simulate thinking typing indicator (random 600-900ms)
        setIsTyping(true);
        const delay = Math.floor(Math.random() * 300) + 600;

        if (typingTimeoutRef.current) {
          clearTimeout(typingTimeoutRef.current);
        }

        const timer = setTimeout(() => {
          const nextNode = FLOW[nextNodeId];
          if (nextNode) {
            setMessages((prev) => [
              ...prev,
              {
                id: `bot-${Date.now()}`,
                type: "bot",
                text: nextNode.message,
                timestamp: new Date(),
              },
            ]);
            setCurrentNodeId(nextNodeId);
            setConversationPath((prev) => [...prev, nextNodeId]);
          }
          setIsTyping(false);
        }, delay);

        typingTimeoutRef.current = timer;
      }, 300);
    },
    [currentNodeId, isTransitioningOptions, isTyping, resetChat, closeChat]
  );

  const goBack = useCallback(() => {
    if (conversationPath.length <= 1 || showEmailForm) return;

    const newPath = [...conversationPath];
    newPath.pop(); // remove last node
    const prevNodeId = newPath[newPath.length - 1];

    setConversationPath(newPath);
    setCurrentNodeId(prevNodeId);
    setCustomOptions(null);

    // Add previous bot message instantly without delay
    const prevNode = FLOW[prevNodeId];
    if (prevNode) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-back-${Date.now()}`,
          type: "bot",
          text: prevNode.message,
          timestamp: new Date(),
        },
      ]);
    }
  }, [conversationPath, showEmailForm]);

  const handleEmailSent = useCallback((formData: { email: string; message: string }) => {
    setEmailSent(true);
    setShowEmailForm(false);

    // 1. Add instant message confirming receipt
    setMessages((prev) => [
      ...prev,
      {
        id: `bot-email-ok-${Date.now()}`,
        type: "bot",
        text: `✅ Message sent! We'll get back to you at ${formData.email} within 24 hours.`,
        timestamp: new Date(),
      },
    ]);

    // 2. Wait 1.5s, then show follow-up questions
    setIsTyping(true);
    setTimeout(() => {
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-email-next-${Date.now()}`,
          type: "bot",
          text: "Is there anything else I can help with?",
          timestamp: new Date(),
        },
      ]);
      setCustomOptions([
        { label: "Start over 🔄", next: "root" },
        { label: "Close chat ❌", action: "close" },
      ]);
    }, 1500);
  }, []);

  const handleManualQuestion = useCallback(async (question: string) => {
    if (isTyping) return;

    // 1. Add user's question bubble
    const userMsgId = `manual-user-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        type: "user",
        text: question,
        timestamp: new Date(),
      },
    ]);

    // 2. Set typing state
    setIsTyping(true);

    try {
      const apiKey = import.meta.env.VITE_GROQ_API_KEY || "";
      const model = import.meta.env.VITE_GROQ_MODEL || "llama-3.3-70b-versatile";

      if (!apiKey) {
        throw new Error("API key is not configured.");
      }

      // Call Groq API with the detailed System Knowledge Card
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: model,
          temperature: 0.5,
          max_tokens: 800,
          messages: [
            { role: "system", content: KNOWLEDGE_CARD },
            { role: "user", content: question }
          ]
        })
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData?.error?.message || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const botResponse = data?.choices?.[0]?.message?.content || "No response received.";

      setMessages((prev) => [
        ...prev,
        {
          id: `bot-manual-${Date.now()}`,
          type: "bot",
          text: botResponse,
          timestamp: new Date(),
        },
      ]);
    } catch (err: any) {
      console.error("Groq API Error:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-manual-err-${Date.now()}`,
          type: "bot",
          text: `⚠️ Groq API issue: ${err.message || "Failed to fetch response."}\n\nPlease check your internet connection or the configured API keys.`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  }, [isTyping]);

  return {
    messages,
    currentNodeId,
    isTyping,
    isOpen,
    conversationPath,
    emailSubject,
    showEmailForm,
    emailSent,
    sessionId,
    customOptions,
    selectedOption,
    isTransitioningOptions,
    openChat,
    closeChat,
    handleOptionSelect,
    goBack,
    handleEmailSent,
    resetChat,
    setShowEmailForm,
    handleManualQuestion,
  };
}
