import sys
import asyncio
import argparse
import random
import string
import math

from functools import partial
from timeit import default_timer as timer

from aiostomp.aiostomp import AioStomp


DEFAULT_NUM_MSGS = 100000
DEFAULT_NUM_PUBS = 1
DEFAULT_NUM_SUBS = 0
DEFAULT_MESSAGE_SIZE = 128


def get_parameters(args):
    parser = argparse.ArgumentParser(description='AioStomp Benchmark')

    parser.add_argument(
        '-np',
        type=int,
        default=DEFAULT_NUM_PUBS,
        help="Number of publishers [default: %(default)s]")

    parser.add_argument(
        '-ns',
        type=int,
        default=DEFAULT_NUM_SUBS,
        help="Number os subscribers [default: %(default)s].")

    parser.add_argument(
        '-n',
        type=int,
        default=DEFAULT_NUM_MSGS,
        help="Number of messages to send [default: %(default)s].")

    parser.add_argument(
        '-ms',
        type=int,
        default=DEFAULT_MESSAGE_SIZE,
        help="Message size [default: %(default)s].")

    parser.add_argument(
        '-csv',
        type=str,
        help="Message size [default: %(default)s].")

    parser.add_argument(
        'server',
        help="Stomp server address [127.0.0.1:61613].")

    parser.add_argument(
        'queue',
        help="Stomp queue to be used.")

    return parser.parse_args(args)


def message_per_client(messages, clients):
    n = messages // clients

    messages_per_client = [n for x in range(clients)]

    remainder = messages % clients

    for x in range(remainder):
        messages_per_client[x] += 1

    return messages_per_client


def human_bytes(bytes_, si=False):
    base = 1024
    pre = ["K", "M", "G", "T", "P", "E"]
    post = "B"
    if si:
        base = 1000
        pre = ["k", "M", "G", "T", "P", "E"]
        post = "iB"

    if bytes_ < float(base):
        return "{:.2f} B".format(bytes_)

    exp = int(math.log(bytes_) / math.log(float(base)))
    index = exp - 1
    units = pre[index] + post
    return "{:.2f} {}".format(bytes_ / math.pow(float(base), float(exp)), units)


class Sample():
    def __init__(self, messages, msg_length, start, end):
        self.messages = messages
        self.msg_length = msg_length
        self.msg_bytes = messages * msg_length
        self.start = start
        self.end = end

    @property
    def rate(self):
        return float(self.messages) / self.duration

    @property
    def duration(self):
        return self.end - self.start

    @property
    def throughput(self):
        return self.msg_bytes / self.duration

    def __str__(self):
        return "{} msgs/sec ~ {}/sec".format(self.rate, human_bytes(self.throughput, si=False))


class SampleGroup(Sample):

    def __init__(self):
        super().__init__(0, 0, 0, 0)
        self.samples = []

    def add_sample(self, sample):
        self.samples.append(sample)

        if len(self.samples) == 1:
            self.start = sample.start
            self.end = sample.end

        self.messages += sample.messages
        self.msg_bytes += sample.msg_bytes

        if sample.start < self.start:
            self.start = sample.start

        if sample.end > self.end:
            self.end = sample.end

    def statistics(self):
        return "min {:.2f} | avg {:.2f} | max {:.2f} | stddev {:.2f} msgs".format(
            self.min_rate,
            self.avg_rate,
            self.max_rate,
            self.std_dev)

    @property
    def min_rate(self):
        for i, s in enumerate(self.samples):
            if i == 0:
                m = s.rate
            m = min(m, s.rate)
        return m

    @property
    def max_rate(self):
        for i, s in enumerate(self.samples):
            if i == 0:
                m = s.rate
            m = max(m, s.rate)
        return m

    @property
    def avg_rate(self):
        sum_ = 0
        for s in self.samples:
            sum_ += s.rate
        return sum_ / len(self.samples)

    @property
    def std_dev(self):
        avg = self.avg_rate
        sum_ = 0

        for c in self.samples:
            sum_ += math.pow(c.rate - avg, 2)

        variance = sum_ / len(self.samples)
        return math.sqrt(variance)


class Benchmark():

    def __init__(self):
        self.subscribe = SampleGroup()
        self.publish = SampleGroup()

    def add_sample(self, sample_type, sample):
        if sample_type == 'subscribe':
            self.subscribe.add_sample(sample)
        elif sample_type == 'publish':
            self.publish.add_sample(sample)

    def report(self):

        if len(self.publish.samples):
            print('\n Publish')
            for i, s in enumerate(self.publish.samples):
                print('[{}] {} ({} msgs)'.format(i + 1, s, s.messages))
            print(self.publish.statistics())

        if len(self.subscribe.samples):
            print('\n Subscribe')
            for i, s in enumerate(self.subscribe.samples):
                print('[{}] {} ({} msgs)'.format(i + 1, s, s.messages))
            print(self.subscribe.statistics())

    def to_csv(self):
        pass


async def create_connection(address, client_id):
    host, port = address.split(':')

    client = AioStomp(host, int(port), client_id=client_id)

    await client.connect()

    return client


async def run_publish(client, bench, message_size, num_msgs, queue):

    msg = ''.join([
        random.choice(string.printable)
        for n in range(message_size)])

    start = timer()
    for n in range(num_msgs):
        client.send(queue, msg)
        await asyncio.sleep(0)

    end = timer()
    bench.add_sample('publish', Sample(num_msgs, message_size, start, end))
    client.close()


async def run_subscribe(client, bench, message_size, num_msgs, queue):

    class Handler:
        def __init__(self, client, bench, message_size, num_msgs):
            self.counter = 0
            self.bench = bench
            self.message_size = message_size
            self.num_msgs = num_msgs
            self.start = timer()

            loop = asyncio.get_event_loop()
            self._waiter = loop.create_future()

        async def handle_message(self, frame, message):
            self.counter += 1

            if self.counter >= self.num_msgs:
                end = timer()
                self.bench.add_sample(
                    'subscribe',
                    Sample(self.counter, self.message_size, self.start, end))

                self._waiter.set_result(True)
                client.close()

        async def wait_complete(self):
            return await self._waiter

    h = Handler(client, bench, message_size, num_msgs)

    client.subscribe(queue, handler=partial(Handler.handle_message, h))

    await h.wait_complete()


async def run_benchmark(params):

    subscribers = []
    publishers = []

    bench = Benchmark()

    for s in range(params.ns):
        subscribers.append(create_connection(
            params.server, 'bench-sub#{}'.format(s)))

    subscribers = await asyncio.gather(*subscribers)

    for s in range(params.np):
        publishers.append(create_connection(
            params.server, 'bench-pub#{}'.format(s)))

    publishers = await asyncio.gather(*publishers)

    tasks = []
    if params.ns != 0:
        sub_messages = params.n // params.ns

    for i, client in enumerate(subscribers):
        tasks.append(
            run_subscribe(client,
                          bench,
                          params.ms,
                          sub_messages,
                          params.queue))

    if params.np != 0:
        pub_messages = message_per_client(params.n, params.np)

    for i, client in enumerate(publishers):
        tasks.append(
            run_publish(client, bench, params.ms, pub_messages[i], params.queue))

    await asyncio.gather(*tasks)

    bench.report()


def main(args=None):

    if args is None:
        args = sys.argv[1:]

    params = get_parameters(args)

    if not params.server or not params.queue:
        return

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_benchmark(params))


if __name__ == '__main__':
    main(sys.argv[1:])
