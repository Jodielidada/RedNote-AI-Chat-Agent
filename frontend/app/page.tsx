'use client';

import { useState } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface PostData {
  title: string;
  content: string;
  type: string;
  has_video: boolean;
  image_count: number;
}

export default function Home() {
  const [step, setStep] = useState<'input' | 'loading' | 'chat'>('input');
  const [url, setUrl] = useState('');
  const [postId, setPostId] = useState('');
  const [postData, setPostData] = useState<PostData | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCrawl = async () => {
    if (!url.trim()) {
      setError('Please enter a post or profile link');
      return;
    }

    setLoading(true);
    setError('');
    setStep('loading');

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15 * 60 * 1000);
      const response = await fetch('/api/crawl', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        let message = 'Crawl failed';
        try {
          const errorData = await response.json();
          message = errorData?.detail || errorData?.message || message;
        } catch {
          message = response.statusText || `Error ${response.status}`;
        }
        throw new Error(typeof message === 'string' ? message : 'Crawl failed');
      }

      const data = await response.json().catch(() => null);
      if (!data) {
        const fallback = response.status === 200
          ? 'Response could not be parsed. Try again or use a shorter profile.'
          : 'Invalid response from server';
        throw new Error(fallback);
      }
      if (!data.data || typeof data.success === 'undefined') {
        throw new Error('Unexpected response shape from server.');
      }

      if (data.success) {
        setPostId(data.post_id ?? '');
        setPostData(data.data);
        setStep('chat');
        const isProfile = data.data?.type === 'profile';
        setMessages([
          {
            role: 'assistant',
            content: isProfile
              ? "Happy to talk with you! Ask me anything."
              : `Hi! I've learned the content of this post. Ask me anything about "${data.data.title || 'it'}".`,
          },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Processing failed, please try again';
      setError(err instanceof Error && err.name === 'AbortError'
        ? 'Request timed out (15 min). Long videos take a while — try again or use a shorter clip.'
        : msg);
      setStep('input');
    } finally {
      setLoading(false);
    }
  };

  // 发送消息
  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: input,
          post_id: postId,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const msg = (data?.detail || data?.message || 'Send failed');
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
        },
      ]);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Sorry, something went wrong: ${errMsg}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // 重新开始
  const handleReset = () => {
    setStep('input');
    setUrl('');
    setPostId('');
    setPostData(null);
    setMessages([]);
    setInput('');
    setError('');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-pink-50 to-red-50">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-red-600 mb-2">
            RedNote AI Chat
          </h1>
          <p className="text-gray-600">
            Enter a single post link or a creator profile link
          </p>
        </div>

        {/* Input */}
        {step === 'input' && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Post or profile link
              </label>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleCrawl()}
                placeholder="https://www.xiaohongshu.com/explore/... or .../user/profile/..."
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
              />
              {error && (
                <p className="mt-2 text-sm text-red-600">{error}</p>
              )}
            </div>

            <button
              onClick={handleCrawl}
              disabled={loading}
              className="w-full bg-red-500 text-white py-3 px-6 rounded-lg font-medium hover:bg-red-600 transition disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {loading ? 'Processing...' : 'Start Analysis'}
            </button>

            <div className="mt-6 text-sm text-gray-500">
              <p className="font-medium mb-2">Features:</p>
              <ul className="list-disc list-inside space-y-1">
                <li>✅ Single post – one note link</li>
                <li>✅ Creator profile</li>
                <li>✅ Video posts – auto transcription; image posts – OCR</li>
                <li>✅ Chat – AI answers based on all content</li>
              </ul>
            </div>
          </div>
        )}

        {/* Loading */}
        {step === 'loading' && (
          <div className="bg-white rounded-2xl shadow-xl p-12 text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-red-500 mx-auto mb-4"></div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">
              Processing content...
            </h2>
            <p className="text-gray-600">
              Extracting post content. Long videos may take 5–15 minutes — please wait.
            </p>
          </div>
        )}

        {/* Chat */}
        {step === 'chat' && postData && (
          <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
            {/* Post info header */}
            <div className="bg-gradient-to-r from-red-500 to-pink-500 text-white p-6">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <h2 className="text-xl font-bold mb-2">
                    {postData.type === 'profile' ? 'Happy to talk with you' : postData.title}
                  </h2>
                  <div className="flex gap-4 text-sm opacity-90">
                    <span>
                      Type: {postData.type === 'profile' ? 'Profile' : postData.type === 'video' ? 'Video' : 'Image'}
                    </span>
                    {postData.has_video && <span>✓ Transcribed</span>}
                    {postData.image_count > 0 && (
                      <span>✓ {postData.image_count} images</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleReset}
                  className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition"
                >
                  New post
                </button>
              </div>
            </div>

            {/* Chat messages */}
            <div className="h-[500px] overflow-y-auto p-6 space-y-4">
              {messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-red-500 text-white'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-2xl px-4 py-3">
                    <div className="flex space-x-2">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '0.1s' }}
                      ></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '0.2s' }}
                      ></div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="border-t p-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) =>
                    e.key === 'Enter' && !loading && handleSend()
                  }
                  placeholder="Ask me anything about this post..."
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  disabled={loading}
                />
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  className="bg-red-500 text-white px-6 py-3 rounded-lg font-medium hover:bg-red-600 transition disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
