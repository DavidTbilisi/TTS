"""Test script to demonstrate streaming audio playback."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from TTS_ka.ultra_fast import smart_generate_long_text


async def test_streaming():
    """Test streaming playback with a long text."""
    
    # Sample long text for testing
    test_text = """
    Hello and welcome to this demonstration of streaming audio playback.
    This is a longer text that will be split into multiple chunks.
    Each chunk will be generated in parallel, and with streaming enabled,
    you should hear the audio start playing before all chunks are finished generating.
    This significantly reduces the perceived latency and provides a better user experience.
    The system will continue generating the remaining audio in the background
    while you're already listening to the first parts.
    This is particularly useful for long texts, articles, or documents.
    Thank you for testing this streaming feature!
    """
    
    print("=" * 60)
    print("STREAMING PLAYBACK TEST")
    print("=" * 60)
    print("\n📝 Testing with long text (multiple chunks)")
    print("🔊 Streaming ENABLED - audio should start quickly\n")
    
    output_path = "test_streaming_output.mp3"
    
    try:
        await smart_generate_long_text(
            text=test_text,
            language='en',
            chunk_seconds=15,  # Smaller chunks to demonstrate streaming
            parallel=4,
            output_path=output_path,
            enable_streaming=True
        )
        
        print("\n✅ Test completed!")
        print(f"📁 Full audio saved to: {output_path}")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()


async def test_without_streaming():
    """Test regular playback without streaming for comparison."""
    
    test_text = """
    This is the same text being generated without streaming.
    You'll notice that there's more delay before playback starts,
    because the system waits for all chunks to be generated and merged
    before playing any audio at all.
    """
    
    print("\n" + "=" * 60)
    print("REGULAR PLAYBACK TEST (No Streaming)")
    print("=" * 60)
    print("\n📝 Testing WITHOUT streaming")
    print("⏳ All chunks will generate first, then play\n")
    
    output_path = "test_no_streaming_output.mp3"
    
    try:
        await smart_generate_long_text(
            text=test_text,
            language='en',
            chunk_seconds=15,
            parallel=4,
            output_path=output_path,
            enable_streaming=False
        )
        
        print("\n✅ Test completed!")
        print(f"📁 Full audio saved to: {output_path}")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")


async def main():
    """Run both tests for comparison."""
    print("\n🎵 TTS STREAMING PLAYBACK TEST SUITE\n")
    
    # Test with streaming
    await test_streaming()
    
    # Small delay between tests
    await asyncio.sleep(2)
    
    # Test without streaming for comparison
    await test_without_streaming()
    
    print("\n" + "=" * 60)
    print("COMPARISON:")
    print("- Streaming: Audio starts playing almost immediately")
    print("- No Streaming: Wait for all generation before playback")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
